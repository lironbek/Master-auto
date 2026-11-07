"""Code-review scan (bounded file selection, Claude mocked), outbound
notifications, and source actions on Vercel / Supabase assets."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from cc import codescan, notify
from cc import profile as profile_engine
from cc import secrets as secrets_mod
from cc import sync as sync_engine
from cc.connectors import AssetRecord, SyncResult
from pt_agent.storage import reset_store_for_tests

os.environ.setdefault("CC_SECRET_KEY", secrets_mod.generate_key())


class FakeRepo:
    provider = "github"
    actions: list = []

    def __init__(self, *a, **k):
        pass

    def verify(self):
        return {"account": "fake", "capabilities": ["inventory"]}

    def sync(self, *, since=None):
        return SyncResult(assets=[AssetRecord(external_id="1", kind="repo", name="acme/app", environment="development"),
                                  AssetRecord(external_id="prj_1", kind="vercel_project", name="app", environment="production")],
                          coverage={"inventory": "full"})

    def list_files(self, full):
        return "main", [("src/auth/login.ts", 900), ("src/api/webhook.ts", 1200), ("README.md", 100), ("node_modules/x/index.js", 50),
                        ("public/logo.png", 5000), ("src/big.ts", 50_000), ("package-lock.json", 90_000), ("src/util.ts", 300)]

    def read_file(self, full, path, ref):
        return f"// {path}\nconst token = 'sk-live-abcdefgh12345';\nexport default 1;\n"

    def delete_project(self, pid):
        FakeRepo.actions.append(("delete", pid)); return {"deleted": True}

    def pause_project(self, pid):
        FakeRepo.actions.append(("pause", pid)); return {"paused": True}


def test_select_files_prioritises_security_relevant_sources():
    chosen = codescan.select_files(FakeRepo().list_files("acme/app")[1])
    assert chosen[:2] == ["src/auth/login.ts", "src/api/webhook.ts"]
    assert "node_modules/x/index.js" not in chosen and "public/logo.png" not in chosen and "src/big.ts" not in chosen and "README.md" not in chosen


def test_parse_review_tolerates_wrapping_text_and_bad_severity():
    out = codescan.parse_review('Here you go:\n{"summary": "ok", "findings": [{"severity": "CRITICAL", "title": "x", "file": "a.ts", "line": "7"}]}')
    assert out["summary"] == "ok" and out["findings"][0]["severity"] == "info" and out["findings"][0]["line"] is None


@pytest.fixture
def client(monkeypatch):
    reset_store_for_tests()
    FakeRepo.actions = []
    for mod in (sync_engine.connectors, profile_engine.connectors):
        monkeypatch.setattr(mod, "build", lambda provider, secret, config: FakeRepo())
    import cc.routes as routes
    monkeypatch.setattr(routes, "build", lambda provider, secret, config: FakeRepo())
    from app import app
    with TestClient(app) as c:
        yield c
    reset_store_for_tests()


def _login(client):
    r = client.post("/auth/register-org", json={"organization_name": "Acme", "email": "admin@acme.io", "password": "correct-horse-battery"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _project_with_assets(client, h):
    ws = client.post("/cc/workspaces", json={"name": "W"}, headers=h).json()
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "App"}, headers=h).json()
    for prov in ("github", "vercel"):
        con = client.post("/cc/connections", json={"workspace_id": ws["id"], "provider": prov, "secret": "tok_x"}, headers=h).json()
        client.post(f"/cc/connections/{con['id']}/sync", headers=h)
    assets = client.get("/cc/assets", headers=h).json()
    for a in assets:
        client.post(f"/cc/projects/{pr['id']}/assets", json={"asset_id": a["id"]}, headers=h)
    return ws, pr, assets


def test_code_scan_sends_redacted_files_and_meters_usage(client, monkeypatch):
    h = _login(client)
    ws, pr, assets = _project_with_assets(client, h)
    # no key -> clear 409
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post(f"/cc/projects/{pr['id']}/scan?kind=code", headers=h)
    assert r.status_code == 409 and "Anthropic key" in r.json()["detail"]

    seen = {}

    def fake_review(api_key, model, full, files):
        seen["files"] = files
        return ({"summary": "two issues", "findings": [
            {"severity": "high", "title": "סוד בקוד", "detail": "token", "fix": "env", "file": "src/auth/login.ts", "line": 2, "source": "code"},
            {"severity": "low", "title": "x", "detail": "", "fix": "", "file": "src/util.ts", "line": None, "source": "code"}]},
                {"input": 1234, "output": 321})

    monkeypatch.setattr(codescan, "review_with_claude", fake_review)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    scan = client.post(f"/cc/projects/{pr['id']}/scan?kind=code", headers=h).json()
    assert scan["kind"] == "code" and scan["grade"] == "C" and scan["files"] == 3 and scan["counts"]["high"] == 1
    assert all("sk-live-abcdefgh12345" not in f["content"] for f in seen["files"])   # redacted before sending
    assert {f["path"] for f in seen["files"]} == {"src/auth/login.ts", "src/api/webhook.ts", "src/util.ts"}
    usage = client.get(f"/cc/usage?workspace_id={ws['id']}", headers=h).json()
    assert usage["totals"] == {"requests": 1, "tokens_in": 1234, "tokens_out": 321}
    assert usage["by_interface"][0]["interface"] == "scan:code"
    detail = client.get(f"/cc/projects/{pr['id']}", headers=h).json()
    assert detail["project"]["last_code_scan_grade"] == "C"


def test_alert_and_bad_scan_notify_webhook_and_email(client, monkeypatch):
    posted = []

    class R:
        status_code = 200

    monkeypatch.setattr(notify.httpx, "post", lambda url, **kw: posted.append((url, kw.get("json"))) or R())
    monkeypatch.setenv("CC_ALERT_WEBHOOK_URL", "https://hooks.example/x")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("CC_ALERT_EMAIL_TO", "me@example.com")
    h = _login(client)
    ws, pr, assets = _project_with_assets(client, h)
    client.post("/cc/report", json={"workspace_id": ws["id"], "service": "x", "external_id": "r1"}, headers={"X-Report-Token": "bad"})
    tok = client.post(f"/cc/workspaces/{ws['id']}/report-token", headers=h).json()["report_token"]
    # a production failure on an assigned reporter asset -> alert -> webhook + email
    client.post("/cc/report", json={"workspace_id": ws["id"], "service": "backup", "external_id": "r2", "result": "success"}, headers={"X-Report-Token": tok})
    rep_asset = [a for a in client.get("/cc/assets", headers=h).json() if a["provider"] == "reporter"][0]
    client.post(f"/cc/projects/{pr['id']}/assets", json={"asset_id": rep_asset["id"]}, headers=h)
    client.post("/cc/report", json={"workspace_id": ws["id"], "service": "backup", "external_id": "r3", "result": "failure", "environment": "production"}, headers={"X-Report-Token": tok})
    urls = [u for u, _ in posted]
    assert "https://hooks.example/x" in urls and "https://api.resend.com/emails" in urls
    assert any(j and j.get("kind") == "failure" for _, j in posted)


def test_source_actions_on_vercel_assets(client):
    h = _login(client)
    ws, pr, assets = _project_with_assets(client, h)
    v = [a for a in assets if a["provider"] == "vercel" and a["kind"] == "vercel_project"][0]
    assert client.post(f"/cc/assets/{v['id']}/source-action", json={"action": "archive", "confirm": "app"}, headers=h).json()["paused"]
    assert client.get(f"/cc/assets/{v['id']}", headers=h).json()["asset"]["state"] == "paused"
    r = client.post(f"/cc/assets/{v['id']}/source-action", json={"action": "delete", "confirm": "app"}, headers=h).json()
    assert r["deleted"] and FakeRepo.actions == [("pause", "prj_1"), ("delete", "prj_1")]
