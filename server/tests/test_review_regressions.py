"""Regressions for the findings of the security / correctness review."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from cc import secrets as secrets_mod
from cc import sync as sync_engine
from cc.connectors import AssetRecord, ConfigError, EventRecord, SyncResult, validate_base_url
from pt_agent.evidence.redaction import RedactionError, assert_clean, redact
from pt_agent.scope.target import TargetParseError, normalize
from pt_agent.storage import reset_store_for_tests

os.environ.setdefault("CC_SECRET_KEY", secrets_mod.generate_key())
KEY = b"test-org-hmac-key-32-bytes-long!!"


# --- redaction ----------------------------------------------------------------

def test_json_quoted_secret_keys_are_redacted():
    body = '{"password": "hunter2secret", "api_key": "sk-live-abcdefgh", "user": "dana"}'
    r = redact(body, org_key=KEY)
    assert "hunter2secret" not in r.text and "sk-live-abcdefgh" not in r.text
    assert '"user": "dana"' in r.text          # non-secret fields untouched
    assert_clean(r.text)                        # the guard agrees


def test_encrypted_pem_with_colon_header_redacts_instead_of_crashing():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nProc-Type: 4,ENCRYPTED\nMIIEow==\n-----END RSA PRIVATE KEY-----"
    r = redact(pem, org_key=KEY)
    assert r.text == "[REDACTED]" and "private_key" in r.hit_kinds


def test_bearer_fingerprint_is_of_the_token_not_the_label():
    a = redact("Authorization: Bearer tokenAAAAAAAA", org_key=KEY).fingerprints["bearer"][0]
    b = redact("Authorization: Bearer tokenBBBBBBBB", org_key=KEY).fingerprints["bearer"][0]
    assert a != b


def test_redacted_kv_keeps_structure_and_passes_guard():
    r = redact("password=TopSecret42 in body", org_key=KEY)
    assert r.text == "password=[REDACTED] in body"
    assert_clean(r.text)


# --- scope / egress -----------------------------------------------------------

def test_percent_encoded_dot_segments_cannot_escape_the_allowed_prefix():
    assert normalize("https://h.example/api/%2e%2e/admin").path == "/admin"
    assert normalize("https://h.example/api/../admin").path == "/admin"
    assert normalize("https://h.example/api/x/./y/").path == "/api/x/y/"
    # Climbing above the root clamps to the root, exactly as a server would.
    assert normalize("https://h.example/%2e%2e/%2e%2e/etc").path == "/etc"
    with pytest.raises(TargetParseError):
        normalize("ftp://h.example/x")


# --- connector config (SSRF guard) ------------------------------------------

@pytest.mark.parametrize("url", ["http://n8n.example.com", "https://localhost", "https://127.0.0.1", "https://10.0.0.5:8080",
                                 "https://user:pw@n8n.example.com", "https://169.254.169.254", "https://metadata.google.internal"])
def test_n8n_base_url_refuses_non_public_targets(url):
    with pytest.raises(ConfigError):
        validate_base_url(url)


# --- control-center API -------------------------------------------------------

class FakeConnector:
    provider = "github"
    assets = [AssetRecord(external_id="101", kind="repo", name="acme/app", environment="development")]
    events = [EventRecord(external_id="run:1", asset_external_id="101", kind="workflow_run", result="failure",
                          occurred_at="2026-11-07T10:00:00+00:00", title="CI main", environment="production")]

    def __init__(self, *a, **k):
        pass

    def verify(self):
        return {"account": "fake", "capabilities": ["inventory"]}

    def sync(self, *, since=None):
        return SyncResult(assets=list(FakeConnector.assets), events=list(FakeConnector.events), coverage={"inventory": "full"})


@pytest.fixture
def client(monkeypatch):
    reset_store_for_tests()
    monkeypatch.setattr(sync_engine.connectors, "build", lambda provider, secret, config: FakeConnector())
    import cc.routes as routes
    monkeypatch.setattr(routes, "build", lambda provider, secret, config: FakeConnector())
    monkeypatch.setattr(routes, "validate_config", lambda provider, config: config)
    from app import app
    with TestClient(app) as c:
        yield c
    reset_store_for_tests()


def _login(client, org="Acme", email="admin@acme.io"):
    r = client.post("/auth/register-org", json={"organization_name": org, "email": email, "password": "correct-horse-battery"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _workspace(client, h):
    return client.post("/cc/workspaces", json={"name": "W", "kind": "work"}, headers=h).json()


def test_report_token_is_never_readable_and_still_authenticates(client):
    h = _login(client)
    ws = _workspace(client, h)
    tok = client.post(f"/cc/workspaces/{ws['id']}/report-token", headers=h).json()["report_token"]
    listed = client.get("/cc/workspaces", headers=h).json()[0]
    assert "report_token" not in listed and "report_token_hash" not in listed
    ok = client.post("/cc/report", json={"workspace_id": ws["id"], "service": "backup", "external_id": "r1"},
                     headers={"X-Report-Token": tok})
    assert ok.status_code == 200 and ok.json()["ok"]
    bad = client.post("/cc/report", json={"workspace_id": ws["id"], "service": "backup", "external_id": "r2"},
                      headers={"X-Report-Token": tok[:-1] + "x"})
    assert bad.status_code == 401


def test_reassign_after_unassign_reactivates_the_link(client):
    h = _login(client)
    ws = _workspace(client, h)
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "P"}, headers=h).json()
    con = client.post("/cc/connections", json={"workspace_id": ws["id"], "provider": "github", "secret": "ghp_x"}, headers=h).json()
    client.post(f"/cc/connections/{con['id']}/sync", headers=h)
    aid = client.get("/cc/assets", headers=h).json()[0]["id"]
    client.post(f"/cc/projects/{pr['id']}/assets", json={"asset_id": aid}, headers=h)
    client.delete(f"/cc/projects/{pr['id']}/assets/{aid}", headers=h)
    assert client.get("/cc/assets", headers=h).json()[0]["project_ids"] == []
    assert client.get("/cc/overview", headers=h).json()["projects"][0]["asset_count"] == 0
    client.post(f"/cc/projects/{pr['id']}/assets", json={"asset_id": aid}, headers=h)
    assert client.get("/cc/assets", headers=h).json()[0]["project_ids"] == [pr["id"]]
    assert [a["id"] for a in client.get(f"/cc/projects/{pr['id']}", headers=h).json()["assets"]] == [aid]


def test_sync_takes_over_seeded_asset_and_does_not_duplicate(client):
    h = _login(client)
    ws = _workspace(client, h)
    from pt_agent.storage import get_store
    store = get_store()
    org = client.get("/auth/me", headers=h).json()["organization"]["id"]
    # A row seeded from an inventory snapshot: no connection, name-only identity.
    store.insert("cc_assets", {"id": "ast_seed", "organization_id": org, "workspace_id": ws["id"], "connection_id": None,
                               "external_id": "acme/app", "kind": "repo", "name": "acme/app", "provider": "github",
                               "environment": "development", "state": "", "url": "", "description": "", "created_at": "2026-11-01T00:00:00+00:00"})
    con = client.post("/cc/connections", json={"workspace_id": ws["id"], "provider": "github", "secret": "ghp_x"}, headers=h).json()
    s = client.post(f"/cc/connections/{con['id']}/sync", headers=h).json()
    assert s["status"] == "ok" and s["new_inbox"] == 0
    assets = client.get("/cc/assets", headers=h).json()
    assert len(assets) == 1 and assets[0]["id"] == "ast_seed"
    assert assets[0]["external_id"] == "101" and assets[0]["connection_id"] == con["id"]


def test_acknowledged_alert_is_not_reopened_by_the_same_failure(client):
    h = _login(client)
    ws = _workspace(client, h)
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "P"}, headers=h).json()
    con = client.post("/cc/connections", json={"workspace_id": ws["id"], "provider": "github", "secret": "ghp_x"}, headers=h).json()
    client.post(f"/cc/connections/{con['id']}/sync", headers=h)
    aid = client.get("/cc/assets", headers=h).json()[0]["id"]
    client.post(f"/cc/projects/{pr['id']}/assets", json={"asset_id": aid}, headers=h)
    alerts = client.get("/cc/alerts", headers=h).json()
    assert len(alerts) == 1 and alerts[0]["kind"] == "failure"
    client.post(f"/cc/alerts/{alerts[0]['id']}", json={"action": "acknowledge"}, headers=h)
    client.post(f"/cc/connections/{con['id']}/sync", headers=h)
    client.get("/cc/overview", headers=h)
    assert [a["status"] for a in client.get("/cc/alerts", headers=h).json()] == ["acknowledged"]


def test_transient_sync_error_is_retryable_not_disconnected(client, monkeypatch):
    h = _login(client)
    ws = _workspace(client, h)
    con = client.post("/cc/connections", json={"workspace_id": ws["id"], "provider": "github", "secret": "ghp_x"}, headers=h).json()

    def boom(self, *, since=None):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(FakeConnector, "sync", boom)
    s = client.post(f"/cc/connections/{con['id']}/sync", headers=h).json()
    assert s["status"] == "error"
    assert all(a["kind"] != "permission" for a in client.get("/cc/alerts", headers=h).json())


def test_changing_connection_target_requires_the_secret_again(client):
    h = _login(client)
    ws = _workspace(client, h)
    con = client.post("/cc/connections", json={"workspace_id": ws["id"], "provider": "n8n", "secret": "n8n_key_1",
                                               "config": {"base_url": "https://n8n.example.com"}}, headers=h).json()
    r = client.patch(f"/cc/connections/{con['id']}", json={"config": {"base_url": "https://attacker.example"}}, headers=h)
    assert r.status_code == 422
    r = client.patch(f"/cc/connections/{con['id']}", json={"config": {"base_url": "https://attacker.example"}, "secret": "n8n_key_2"}, headers=h)
    assert r.status_code == 200 and "secret_enc" not in r.json()


def test_agent_update_cannot_point_at_another_workspace(client):
    h = _login(client)
    ws1, ws2 = _workspace(client, h), client.post("/cc/workspaces", json={"name": "W2"}, headers=h).json()
    p2 = client.post("/cc/projects", json={"workspace_id": ws2["id"], "name": "P2"}, headers=h).json()
    a = client.post("/cc/agents", json={"workspace_id": ws1["id"], "name": "A", "owner": "Dana"}, headers=h).json()
    r = client.patch(f"/cc/agents/{a['id']}", json={"workspace_id": ws1["id"], "name": "A", "project_id": p2["id"]}, headers=h)
    assert r.status_code == 422
    r = client.patch(f"/cc/agents/{a['id']}", json={"workspace_id": ws1["id"], "name": "A2"}, headers=h)
    assert r.json()["owner"] == "Dana"      # an edit without owner keeps it


def test_negative_amounts_and_budgets_are_rejected(client):
    h = _login(client)
    ws = _workspace(client, h)
    assert client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "P", "budget_usd": -5}, headers=h).status_code == 422
    assert client.post("/cc/costs", json={"workspace_id": ws["id"], "provider": "vercel", "amount": -100}, headers=h).status_code == 422


def test_archived_projects_are_listed_with_status(client):
    h = _login(client)
    ws = _workspace(client, h)
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "P"}, headers=h).json()
    client.patch(f"/cc/projects/{pr['id']}", json={"status": "archived"}, headers=h)
    ov = client.get("/cc/overview", headers=h).json()
    assert [p["status"] for p in ov["projects"]] == ["archived"]
    assert client.patch(f"/cc/projects/{pr['id']}", json={"status": "deleted"}, headers=h).status_code == 422


def test_pt_link_requires_manager_role(client):
    h = _login(client)
    ws = _workspace(client, h)
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "P"}, headers=h).json()
    ptp = client.post("/pt/projects", json={"name": "Survey"}, headers=h).json()
    client.post("/auth/users", json={"email": "dev@acme.io", "password": "correct-horse-battery", "role": "developer"}, headers=h)
    hd = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'dev@acme.io', 'password': 'correct-horse-battery'}).json()['token']}"}
    client.post(f"/cc/workspaces/{ws['id']}/members", json={"user_id": client.get("/auth/users", headers=h).json()[1]["id"], "role": "editor"}, headers=h)
    assert client.post(f"/cc/projects/{pr['id']}/pt", json={"pt_project_id": ptp["id"]}, headers=hd).status_code == 403
    assert client.post(f"/cc/projects/{pr['id']}/pt", json={"pt_project_id": ptp["id"]}, headers=h).status_code == 200


def test_finding_free_text_is_redacted_and_status_note_too(client):
    h = _login(client)
    p = client.post("/pt/projects", json={"name": "P"}, headers=h).json()
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    a = client.post(f"/pt/projects/{p['id']}/authorizations", json={"approver_name": "a", "approver_authority": "b",
                    "valid_from": (now - timedelta(hours=1)).isoformat(), "valid_until": (now + timedelta(hours=1)).isoformat(),
                    "control_verified": True}, headers=h).json()
    s = client.post(f"/pt/projects/{p['id']}/scope-versions", json={"authorization_id": a["id"], "targets": [
        {"scheme": "https", "host": "app.test.example", "ports": [443], "allowed_paths": ["/"]}]}, headers=h).json()
    client.post(f"/pt/scope-versions/{s['id']}/approve", headers=h)
    run = client.post("/pt/runs", json={"scope_version_id": s["id"]}, headers=h).json()
    f = client.post("/pt/findings", json={"run_id": run["id"], "title": "Leak", "asset_path": "/",
                                          "reproduction": "send Authorization: Bearer eyJabc.def.ghi1234", "status": "fixed",
                                          "project_id": "prj_other", "id": "find_forged"}, headers=h).json()
    assert f["status"] == "new" and f["project_id"] == p["id"] and f["id"] != "find_forged"
    assert "ghi1234" not in f["reproduction"]
    client.post(f"/pt/findings/{f['id']}/status", json={"status": "in_review", "note": "repro with password=Hunter2!"}, headers=h)
    audit = client.get("/pt/audit", headers=h).json()
    assert all("Hunter2!" not in e["detail"] for e in audit)


def test_run_window_is_enforced(client):
    h = _login(client)
    p = client.post("/pt/projects", json={"name": "P"}, headers=h).json()
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    a = client.post(f"/pt/projects/{p['id']}/authorizations", json={"approver_name": "a", "approver_authority": "b",
                    "valid_from": (now - timedelta(hours=1)).isoformat(), "valid_until": (now + timedelta(days=2)).isoformat(),
                    "control_verified": True}, headers=h).json()
    s = client.post(f"/pt/projects/{p['id']}/scope-versions", json={"authorization_id": a["id"], "targets": [
        {"scheme": "https", "host": "app.test.example", "ports": [443], "allowed_paths": ["/"]}],
        "run_window_start": (now + timedelta(days=1)).isoformat(), "run_window_end": (now + timedelta(days=2)).isoformat()}, headers=h).json()
    client.post(f"/pt/scope-versions/{s['id']}/approve", headers=h)
    r = client.post("/pt/runs", json={"scope_version_id": s["id"]}, headers=h)
    assert r.status_code == 409 and "window" in r.json()["detail"]
