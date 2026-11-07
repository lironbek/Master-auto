"""Control Center API: workspaces, projects, connections + sync, inbox, sessions,
costs, keys, agents. Mirrors the PRD section 8 acceptance table."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from cc import secrets as secrets_mod
from cc import sync as sync_engine
from cc.connectors import AssetRecord, EventRecord, SyncResult
from pt_agent.storage import reset_store_for_tests

os.environ.setdefault("CC_SECRET_KEY", secrets_mod.generate_key())


class FakeConnector:
    """Deterministic provider used in place of the real connectors."""
    provider = "github"
    calls = 0

    def __init__(self, *a, **k):
        pass

    def verify(self):
        return {"account": "fake", "capabilities": ["inventory", "actions"]}

    def sync(self, *, since=None):
        FakeConnector.calls += 1
        return SyncResult(
            assets=[AssetRecord(external_id="1", kind="repo", name="acme/app", environment="development", url="https://gh/acme/app"),
                    AssetRecord(external_id="2", kind="repo", name="acme/lib", environment="development")],
            events=[EventRecord(external_id="run:1:1", asset_external_id="1", kind="workflow_run", result="failure",
                                occurred_at="2026-11-07T10:00:00+00:00", title="CI main", environment="production"),
                    EventRecord(external_id="pr:1", asset_external_id="1", kind="pull_request", result="running",
                                occurred_at="2026-11-07T09:00:00+00:00", title="PR #1")],
            coverage={"inventory": "full", "actions": "full"},
        )


@pytest.fixture
def client(monkeypatch):
    reset_store_for_tests()
    monkeypatch.setattr(sync_engine.connectors, "build", lambda provider, secret, config: FakeConnector())
    import cc.routes as routes
    monkeypatch.setattr(routes, "build", lambda provider, secret, config: FakeConnector())
    from app import app
    with TestClient(app) as c:
        yield c
    reset_store_for_tests()


def _login(client, org="Acme", email="admin@acme.io"):
    r = client.post("/auth/register-org", json={"organization_name": org, "email": email, "password": "correct-horse-battery"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _workspace(client, h, name="קומקס"):
    return client.post("/cc/workspaces", json={"name": name, "kind": "work"}, headers=h).json()


def test_full_flow_connection_sync_inbox_assign_session_cost(client):
    h = _login(client)
    ws = _workspace(client, h)
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "שילוט COMAX", "owner": "לירון", "budget_usd": 40}, headers=h).json()

    # Connection is verified before saving; secret is never returned.
    con = client.post("/cc/connections", json={"workspace_id": ws["id"], "provider": "github", "secret": "ghp_secret_value", "config": {"repos": "acme/app"}}, headers=h)
    assert con.status_code == 200, con.text
    con = con.json()
    assert con["status"] == "ok" and "secret_enc" not in con and con["secret_masked"].endswith("alue")

    # Sync: assets + events ingested, new assets land in the inbox.
    s = client.post(f"/cc/connections/{con['id']}/sync", headers=h).json()
    assert s["assets"] == 2 and s["events"] == 2 and s["new_inbox"] == 2 and s["status"] == "ok"
    # Re-sync is idempotent: no duplicate assets/events (acceptance: "ייבוא חוזר").
    s2 = client.post(f"/cc/connections/{con['id']}/sync", headers=h).json()
    assert s2["new_inbox"] == 0
    assets = client.get("/cc/assets", headers=h).json()
    assert len(assets) == 2
    events = client.get("/cc/events", headers=h).json()
    assert len(events) == 2 and events[0]["kind"] == "workflow_run"   # newest first

    # Inbox: assign one asset to the project; the event becomes a project failure.
    inbox = client.get("/cc/inbox", headers=h).json()
    item = next(i for i in inbox if i["asset"]["name"] == "acme/app")
    assert client.post(f"/cc/inbox/{item['id']}", json={"action": "assign", "project_id": pr["id"]}, headers=h).json()["ok"]
    assert len(client.get("/cc/inbox", headers=h).json()) == 1
    detail = client.get(f"/cc/projects/{pr['id']}", headers=h).json()
    assert [a["name"] for a in detail["assets"]] == ["acme/app"]
    assert detail["events"][0]["result"] == "failure"
    # Manual description survives the next sync (PRD 4.4).
    aid = detail["assets"][0]["id"]
    client.patch(f"/cc/assets/{aid}", json={"description": "קוד מערכת השילוט"}, headers=h)
    client.post(f"/cc/connections/{con['id']}/sync", headers=h)
    assert client.get(f"/cc/assets/{aid}", headers=h).json()["asset"]["description"] == "קוד מערכת השילוט"

    # Overview reflects the failure and the one unassigned asset.
    ov = client.get("/cc/overview", headers=h).json()
    assert ov["projects"][0]["tone"] == "bad" and ov["unassigned"] == 1 and ov["inbox_open"] == 1
    assert any(a["kind"] == "failure" for a in ov["critical_alerts"])

    # Session: create, link the failure event, close with an outcome.
    ses = client.post("/cc/sessions", json={"project_id": pr["id"], "title": "סידור משתני מבצע", "tool": "claude_code"}, headers=h).json()
    assert ses["status"] == "open"
    sd = client.get(f"/cc/sessions/{ses['id']}", headers=h).json()
    assert len(sd["suggested_events"]) >= 1          # proposed, not auto-linked (PRD 2.3)
    client.post(f"/cc/sessions/{ses['id']}/events", json={"event_id": sd["suggested_events"][0]["id"]}, headers=h)
    sd = client.get(f"/cc/sessions/{ses['id']}", headers=h).json()
    assert len(sd["events"]) == 1
    done = client.patch(f"/cc/sessions/{ses['id']}", json={"status": "done", "outcome": "PR #1"}, headers=h).json()
    assert done["status"] == "done" and done["ended_at"]

    # Costs: a reported charge and the project summary.
    c = client.post("/cc/costs", json={"workspace_id": ws["id"], "project_id": pr["id"], "provider": "Vercel", "kind": "allocation", "amount": 8, "period_start": "2026-11-01", "period_end": "2026-11-30"}, headers=h)
    assert c.status_code == 200
    costs = client.get(f"/cc/costs?project_id={pr['id']}", headers=h).json()
    assert costs["total_usd"] == 8.0 and costs["includes_estimates"] is False


def test_workspace_isolation_and_roles(client):
    h = _login(client)
    ws_a = _workspace(client, h, "A")
    ws_b = _workspace(client, h, "B")
    pa = client.post("/cc/projects", json={"workspace_id": ws_a["id"], "name": "PA"}, headers=h).json()
    # A viewer in workspace B must not see workspace A at all.
    client.post("/auth/users", json={"email": "viewer@acme.io", "password": "viewer-pass-1", "role": "developer"}, headers=h)
    uid = next(u["id"] for u in client.get("/auth/users", headers=h).json() if u["email"] == "viewer@acme.io")
    client.post(f"/cc/workspaces/{ws_b['id']}/members", json={"user_id": uid, "role": "viewer"}, headers=h)
    vh = {"Authorization": f"Bearer {client.post('/auth/login', json={'email': 'viewer@acme.io', 'password': 'viewer-pass-1'}).json()['token']}"}
    assert [w["id"] for w in client.get("/cc/workspaces", headers=vh).json()] == [ws_b["id"]]
    assert client.get(f"/cc/projects/{pa['id']}", headers=vh).status_code == 404
    assert client.post("/cc/projects", json={"workspace_id": ws_b["id"], "name": "X"}, headers=vh).status_code == 403
    # Another organisation sees nothing, even with the id.
    oh = _login(client, "Other", "o@other.io")
    assert client.get(f"/cc/projects/{pa['id']}", headers=oh).status_code == 404
    assert client.get("/cc/overview", headers=oh).json()["projects"] == []


def test_connection_requires_secret_key(client, monkeypatch):
    h = _login(client)
    ws = _workspace(client, h)
    monkeypatch.delenv("CC_SECRET_KEY")
    r = client.post("/cc/connections", json={"workspace_id": ws["id"], "provider": "github", "secret": "ghp_x"}, headers=h)
    assert r.status_code == 503   # refuses to store in clear


def test_keys_agents_and_runs(client):
    h = _login(client)
    ws = _workspace(client, h)
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "BuildFlow", "budget_usd": 80}, headers=h).json()
    other_ws = _workspace(client, h, "אחר")
    key = client.post("/cc/keys", json={"workspace_id": ws["id"], "name": "Anthropic · BuildFlow", "secret": "sk-ant-not-a-real-key-0000"}, headers=h).json()
    assert key["masked"].endswith("0000") and "secret_enc" not in key
    # A key from another workspace is rejected server-side (PRD 9.5).
    other_key = client.post("/cc/keys", json={"workspace_id": other_ws["id"], "name": "k2", "secret": "sk-ant-xxxxxxxx"}, headers=h).json()
    bad = client.post("/cc/agents", json={"workspace_id": ws["id"], "name": "A", "key_id": other_key["id"]}, headers=h)
    assert bad.status_code == 422

    agent = client.post("/cc/agents", json={"workspace_id": ws["id"], "name": "מעקב BuildFlow", "project_id": pr["id"],
                                            "instructions": "סכם מצב", "key_id": None}, headers=h).json()
    assert agent["version"] == 1
    # Dedicated agent cannot run on another project.
    pr2 = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "Other"}, headers=h).json()
    assert client.post(f"/cc/agents/{agent['id']}/runs", json={"project_id": pr2["id"]}, headers=h).status_code == 403

    # Run (no provider key configured -> deterministic summary), idempotent on key.
    r1 = client.post(f"/cc/agents/{agent['id']}/runs", json={"project_id": pr["id"], "idempotency_key": "click-1"}, headers=h).json()
    r2 = client.post(f"/cc/agents/{agent['id']}/runs", json={"project_id": pr["id"], "idempotency_key": "click-1"}, headers=h).json()
    assert r1["id"] == r2["id"] and r1["status"] == "completed" and "BuildFlow" in r1["result"]
    assert [s["tool"] for s in r1["steps"]] == ["catalog.read", "summary.deterministic"]
    runs = client.get(f"/cc/runs?project_id={pr['id']}", headers=h).json()
    assert len(runs) == 1

    # Disabled agent cannot run; version bumps on edit.
    upd = client.patch(f"/cc/agents/{agent['id']}", json={**{k: agent[k] for k in ("workspace_id", "project_id", "name", "instructions", "provider", "model", "tools", "allowed_projects", "limits", "approval_rule")}, "enabled": False}, headers=h).json()
    assert upd["version"] == 2
    assert client.post(f"/cc/agents/{agent['id']}/runs", json={"project_id": pr["id"]}, headers=h).status_code == 409

    # Key rotation reports what is affected.
    client.patch(f"/cc/projects/{pr['id']}", json={"default_key_id": key["id"]}, headers=h)
    rot = client.post(f"/cc/keys/{key['id']}/rotate", json={"secret": "sk-ant-new-key-1111"}, headers=h).json()
    assert rot["version"] == 2 and rot["affected"]["projects"] == ["BuildFlow"]


def test_external_report_signed_and_deduplicated(client):
    h = _login(client)
    ws = _workspace(client, h)
    tok = client.post(f"/cc/workspaces/{ws['id']}/report-token", headers=h).json()["report_token"]
    body = {"workspace_id": ws["id"], "service": "nightly-backup", "external_id": "run-77", "kind": "heartbeat", "result": "success"}
    assert client.post("/cc/report", json=body, headers={"X-Report-Token": "wrong"}).status_code == 401
    first = client.post("/cc/report", json=body, headers={"X-Report-Token": tok}).json()
    again = client.post("/cc/report", json=body, headers={"X-Report-Token": tok}).json()
    assert first["duplicate"] is False and again["duplicate"] is True and first["event_id"] == again["event_id"]
    assert len(client.get("/cc/events", headers=h).json()) == 1
    item = client.get("/cc/inbox", headers=h).json()[0]
    assert item["asset"]["kind"] == "service"
    # Once assigned, a production failure from the reporter raises an alert too.
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "Ops"}, headers=h).json()
    client.post(f"/cc/inbox/{item['id']}", json={"action": "assign", "project_id": pr["id"]}, headers=h)
    client.post("/cc/report", json={**body, "external_id": "run-78", "result": "failure"}, headers={"X-Report-Token": tok})
    assert any(a["kind"] == "failure" for a in client.get("/cc/alerts", headers=h).json())


def test_cron_sync_requires_secret(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "cron-s")
    assert client.get("/cc/sync/all").status_code == 401
    assert client.get("/cc/sync/all", headers={"Authorization": "Bearer cron-s"}).status_code == 200


def test_pt_module_mounted_and_linked(client):
    h = _login(client)
    ws = _workspace(client, h)
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "Site"}, headers=h).json()
    assert client.get("/pt/healthz").status_code == 200
    ptp = client.post("/pt/projects", json={"name": "סקר אתר"}, headers=h).json()
    client.post(f"/cc/projects/{pr['id']}/pt", json={"pt_project_id": ptp["id"]}, headers=h)
    d = client.get(f"/cc/projects/{pr['id']}", headers=h).json()
    assert [x["id"] for x in d["pt_projects"]] == [ptp["id"]]
