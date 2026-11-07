"""Connectors: field allow-listing, error classification, partial coverage (PRD 4, 6)."""

from __future__ import annotations

import json

import httpx
import pytest

from cc.connectors import ConnectorError, GitHubConnector, N8nConnector, SupabaseConnector, VercelConnector
from cc.connectors import base as cbase


@pytest.fixture
def patched_client(monkeypatch):
    """Route every connector HTTP call through a MockTransport handler."""
    routes: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url.host}{request.url.path}"
        for k, v in sorted(routes.items(), key=lambda kv: -len(kv[0])):  # longest prefix wins
            if key.startswith(k):
                if callable(v):
                    return v(request)
                status, body = v
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={"message": "no route " + key})

    def make_client(headers, *, timeout=20.0):
        return httpx.Client(timeout=timeout, headers=headers, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(cbase, "make_client", make_client)
    for mod in ("github", "vercel", "supabase", "n8n"):
        monkeypatch.setattr(__import__(f"cc.connectors.{mod}", fromlist=["make_client"]), "make_client", make_client)
    return routes


def test_github_inventory_prs_runs_allowlisted_fields(patched_client):
    r = patched_client
    r["GET api.github.com/user"] = (200, {"login": "liron"})
    r["GET api.github.com/repos/acme/app"] = (200, {"id": 1, "full_name": "acme/app", "html_url": "https://github.com/acme/app",
                                                   "private": True, "pushed_at": "2026-11-07T10:00:00Z", "description": "x", "default_branch": "main",
                                                   "secret_env": "MUST-NOT-LEAK"})
    r["GET api.github.com/repos/acme/app/pulls"] = (200, [{"id": 42, "number": 7, "title": "Add promo", "state": "open", "updated_at": "2026-11-07T11:00:00Z",
                                                          "html_url": "https://github.com/acme/app/pull/7", "head": {"ref": "feature/x"}, "body": "SECRET BODY"}])
    r["GET api.github.com/repos/acme/app/actions/runs"] = (200, {"workflow_runs": [{"id": 9, "run_attempt": 2, "name": "CI", "head_branch": "main",
                                                                                   "status": "completed", "conclusion": "failure", "updated_at": "2026-11-07T11:30:00Z",
                                                                                   "html_url": "https://github.com/acme/app/actions/runs/9", "head_sha": "abcdef1234567890", "event": "push"}]})
    c = GitHubConnector("tok", repos=["acme/app"])
    assert c.verify()["account"] == "liron"
    res = c.sync()
    assert [a.name for a in res.assets] == ["acme/app"]
    kinds = {e.kind: e for e in res.events}
    assert kinds["pull_request"].result == "running" and kinds["workflow_run"].result == "failure"
    assert kinds["workflow_run"].external_id == "run:9:2"   # attempt-aware identity (PRD 6)
    dumped = json.dumps([a.__dict__ for a in res.assets] + [e.__dict__ for e in res.events])
    assert "MUST-NOT-LEAK" not in dumped and "SECRET BODY" not in dumped


def test_github_actions_forbidden_marks_partial(patched_client):
    r = patched_client
    r["GET api.github.com/repos/acme/app/pulls"] = (200, [])
    r["GET api.github.com/repos/acme/app/actions/runs"] = (403, {"message": "forbidden"})
    r["GET api.github.com/repos/acme/app"] = (200, {"id": 1, "full_name": "acme/app"})
    res = GitHubConnector("tok", repos=["acme/app"]).sync()
    assert res.partial and res.coverage["actions"] == "blocked"


def test_github_unauthorized_classified_as_reauth(patched_client):
    patched_client["GET api.github.com/user"] = (401, {"message": "bad credentials"})
    with pytest.raises(ConnectorError) as exc:
        GitHubConnector("bad").verify()
    assert exc.value.status == "reauth"


def test_vercel_projects_and_deployments(patched_client):
    r = patched_client
    r["GET api.vercel.com/v2/user"] = (200, {"user": {"username": "liron"}})
    r["GET api.vercel.com/v9/projects"] = (200, {"projects": [{"id": "prj_1", "name": "signage", "accountId": "team", "framework": "vite",
                                                              "link": {"org": "acme", "repo": "app", "repoId": 1}, "updatedAt": 1794000000000}]})
    r["GET api.vercel.com/v6/deployments"] = (200, {"deployments": [
        {"uid": "dpl_a", "readyState": "ERROR", "target": None, "createdAt": 1794000100000, "url": "x.vercel.app", "meta": {"githubCommitRef": "feat", "githubCommitSha": "a1b2c3d4e5f6a7b8"}},
        {"uid": "dpl_b", "readyState": "READY", "target": "production", "createdAt": 1794000200000, "url": "y.vercel.app", "meta": {}},
    ]})
    c = VercelConnector("tok", team_id="team_1")
    assert c.verify()["account"] == "liron"
    res = c.sync()
    assert res.assets[0].meta["linked_repo"] == "acme/app"
    envs = {e.external_id: (e.environment, e.result) for e in res.events}
    assert envs["dpl:dpl_a"] == ("preview", "failure") and envs["dpl:dpl_b"] == ("production", "success")


def test_supabase_projects(patched_client):
    r = patched_client
    r["GET api.supabase.com/v1/organizations"] = (200, [{"name": "lironbek's Org"}])
    r["GET api.supabase.com/v1/projects"] = (200, [{"id": "abc", "name": "pt", "status": "ACTIVE_HEALTHY", "region": "eu-central-1", "created_at": "2026-11-07T05:58:20Z"}])
    c = SupabaseConnector("tok")
    assert "lironbek" in c.verify()["account"]
    res = c.sync()
    assert res.assets[0].kind == "supabase_project" and res.assets[0].state == "ACTIVE_HEALTHY"


def test_n8n_inventory_only_when_executions_forbidden(patched_client):
    r = patched_client
    r["GET n8n.example/api/v1/workflows"] = (200, {"data": [{"id": 5, "name": "reminders", "active": True, "updatedAt": "2026-11-07T08:40:00Z"}]})
    r["GET n8n.example/api/v1/executions"] = (403, {"message": "scope"})
    res = N8nConnector("key", base_url="https://n8n.example").sync()
    assert res.partial and res.coverage["executions"] == "inventory_only"
    assert res.assets[0].state == "active" and not res.events
