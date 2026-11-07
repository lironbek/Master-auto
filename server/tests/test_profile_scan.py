"""Project profile ("how is it built") and health scan over fake connectors."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from cc import secrets as secrets_mod
from cc import profile as profile_engine
from cc import sync as sync_engine
from cc.connectors import AssetRecord, SyncResult
from pt_agent.storage import reset_store_for_tests

os.environ.setdefault("CC_SECRET_KEY", secrets_mod.generate_key())


class FakeGitHub:
    provider = "github"

    def __init__(self, *a, **k):
        pass

    def verify(self):
        return {"account": "fake", "capabilities": ["inventory"]}

    def sync(self, *, since=None):
        return SyncResult(assets=[AssetRecord(external_id="1", kind="repo", name="acme/app", environment="development")], coverage={"inventory": "full"})

    def repo_profile(self, full):
        return {"full_name": full, "default_branch": "main", "languages": {"TypeScript": 900, "Python": 100}, "framework": "Next.js",
                "dependencies": {"next": "15", "@anthropic-ai/sdk": "0.5", "@supabase/supabase-js": "2"}, "integrations": ["Claude", "Supabase", "Next.js"],
                "workflows": [], "has_tests": False, "has_readme": True, "env_files_committed": [".env"], "manifests": ["package.json"], "license": ""}

    def repo_health(self, full, prof):
        return [{"severity": "high", "title": "קובץ .env נמצא בריפו", "detail": ".env", "fix": "הסר", "source": "github"},
                {"severity": "medium", "title": "לא נמצאו בדיקות", "detail": "", "fix": "", "source": "github"}]


@pytest.fixture
def client(monkeypatch):
    reset_store_for_tests()
    monkeypatch.setattr(sync_engine.connectors, "build", lambda provider, secret, config: FakeGitHub())
    monkeypatch.setattr(profile_engine.connectors, "build", lambda provider, secret, config: FakeGitHub())
    import cc.routes as routes
    monkeypatch.setattr(routes, "build", lambda provider, secret, config: FakeGitHub())
    from app import app
    with TestClient(app) as c:
        yield c
    reset_store_for_tests()


def _login(client):
    r = client.post("/auth/register-org", json={"organization_name": "Acme", "email": "admin@acme.io", "password": "correct-horse-battery"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_profile_and_scan_flow(client):
    h = _login(client)
    ws = client.post("/cc/workspaces", json={"name": "W"}, headers=h).json()
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "App"}, headers=h).json()
    con = client.post("/cc/connections", json={"workspace_id": ws["id"], "provider": "github", "secret": "ghp_x"}, headers=h).json()
    client.post(f"/cc/connections/{con['id']}/sync", headers=h)
    aid = client.get("/cc/assets", headers=h).json()[0]["id"]
    client.post(f"/cc/projects/{pr['id']}/assets", json={"asset_id": aid}, headers=h)

    prof = client.post(f"/cc/projects/{pr['id']}/profile", headers=h).json()
    assert prof["summary"]["frameworks"] == ["Next.js"] and "Claude" in prof["summary"]["integrations"]
    assert prof["summary"]["languages"]["TypeScript"] == 90
    assert prof["assets"][0]["profile"]["framework"] == "Next.js"

    scan = client.post(f"/cc/projects/{pr['id']}/scan", headers=h).json()
    assert scan["grade"] == "C" and scan["counts"]["high"] == 1 and scan["counts"]["medium"] == 1
    assert scan["findings"][0]["severity"] == "high" and scan["findings"][0]["asset_name"] == "acme/app"

    detail = client.get(f"/cc/projects/{pr['id']}", headers=h).json()
    assert detail["project"]["last_scan_grade"] == "C" and detail["last_scan"]["id"] == scan["id"]
    assert detail["profile"]["summary"]["text"].startswith("App: 1 ריפוזיטוריז")
    assert client.get(f"/cc/projects/{pr['id']}/scans", headers=h).json()[0]["id"] == scan["id"]
    assert client.get(f"/cc/scans/{scan['id']}", headers=h).json()["findings"]
    # the agent context now carries the architecture summary
    from cc.agents import gather_context
    from pt_agent.storage import get_store
    org = client.get("/auth/me", headers=h).json()["organization"]["id"]
    ctx = gather_context(get_store(), org, get_store().get("cc_projects", pr["id"], organization_id=org))
    assert "Next.js" in ctx["architecture"] and ctx["last_scan"]["grade"] == "C"


def test_scan_without_connection_reports_not_scanned(client):
    h = _login(client)
    ws = client.post("/cc/workspaces", json={"name": "W"}, headers=h).json()
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "Bare"}, headers=h).json()
    scan = client.post(f"/cc/projects/{pr['id']}/scan", headers=h).json()
    assert scan["grade"] == "A" and scan["assets"] == 0 and scan["findings"] == []
