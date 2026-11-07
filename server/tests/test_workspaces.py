"""Workspaces as categories: counts, rename, archive, moving projects between
workspaces, and classifying assets under a project in another workspace."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from cc import secrets as secrets_mod
from pt_agent.storage import get_store, reset_store_for_tests

os.environ.setdefault("CC_SECRET_KEY", secrets_mod.generate_key())


@pytest.fixture
def client():
    reset_store_for_tests()
    from app import app
    with TestClient(app) as c:
        yield c
    reset_store_for_tests()


def _login(client):
    r = client.post("/auth/register-org", json={"organization_name": "Acme", "email": "admin@acme.io", "password": "correct-horse-battery"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_move_project_and_archive_workspace(client):
    h = _login(client)
    private = client.post("/cc/workspaces", json={"name": "פרטי", "kind": "personal"}, headers=h).json()
    comax = client.post("/cc/workspaces", json={"name": "Comax", "kind": "work"}, headers=h).json()
    trash = client.post("/cc/workspaces", json={"name": "למחיקה", "kind": "trash"}, headers=h).json()
    assert client.post("/cc/workspaces", json={"name": "x", "kind": "bogus"}, headers=h).status_code == 422

    pr = client.post("/cc/projects", json={"workspace_id": private["id"], "name": "App"}, headers=h).json()
    ses = client.post("/cc/sessions", json={"project_id": pr["id"], "title": "s", "tool": "manual"}, headers=h).json()
    org = client.get("/auth/me", headers=h).json()["organization"]["id"]
    store = get_store()
    store.insert("cc_assets", {"id": "ast_1", "organization_id": org, "workspace_id": private["id"], "connection_id": None, "external_id": "1",
                               "kind": "repo", "name": "acme/app", "provider": "github", "environment": "development", "state": "", "url": "", "description": ""})
    client.post(f"/cc/projects/{pr['id']}/assets", json={"asset_id": "ast_1"}, headers=h)

    listed = {w["name"]: w for w in client.get("/cc/workspaces", headers=h).json()}
    assert listed["פרטי"]["projects"] == 1 and listed["פרטי"]["assets"] == 1 and listed["Comax"]["projects"] == 0

    # still holds a project -> refuse to archive
    assert client.delete(f"/cc/workspaces/{private['id']}", headers=h).status_code == 409

    r = client.post(f"/cc/projects/{pr['id']}/move", json={"workspace_id": comax["id"]}, headers=h).json()
    assert r["project"]["workspace_id"] == comax["id"] and r["moved"] == 1
    detail = client.get(f"/cc/projects/{pr['id']}", headers=h).json()
    assert detail["project"]["workspace_id"] == comax["id"]
    assert [a["id"] for a in detail["assets"]] == ["ast_1"]          # link kept, asset stays in its workspace
    assert detail["sessions"][0]["id"] == ses["id"]                  # session followed the project
    assert client.get(f"/cc/overview?workspace_id={comax['id']}", headers=h).json()["projects"][0]["id"] == pr["id"]
    assert client.get(f"/cc/overview?workspace_id={private['id']}", headers=h).json()["projects"] == []

    # an asset from the private workspace can be classified under a Comax project
    store.insert("cc_assets", {"id": "ast_2", "organization_id": org, "workspace_id": private["id"], "connection_id": None, "external_id": "2",
                               "kind": "repo", "name": "acme/other", "provider": "github", "environment": "development", "state": "", "url": "", "description": ""})
    assert client.post(f"/cc/projects/{pr['id']}/assets", json={"asset_id": "ast_2"}, headers=h).status_code == 200

    # rename + archive the now-empty workspace; archived ones disappear from the list
    assert client.patch(f"/cc/workspaces/{trash['id']}", json={"name": "למחיקה בקרוב"}, headers=h).json()["name"] == "למחיקה בקרוב"
    assert client.delete(f"/cc/workspaces/{private['id']}", headers=h).status_code == 200
    names = {w["name"] for w in client.get("/cc/workspaces", headers=h).json()}
    assert names == {"Comax", "למחיקה בקרוב"}
    assert client.post(f"/cc/projects/{pr['id']}/move", json={"workspace_id": private["id"]}, headers=h).status_code == 422
