"""Postgres integration: migration idempotence, store scoping, API flow.

Skipped unless ``PT_TEST_DATABASE_URL`` points at a disposable database.
"""

from __future__ import annotations

import os

import pytest

DSN = os.environ.get("PT_TEST_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="PT_TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def migrated():
    from pt_agent.db.migrate import migrate

    first = migrate(DSN)
    second = migrate(DSN)
    assert second == []  # idempotent
    return first


@pytest.fixture
def store(migrated):
    from pt_agent.storage.postgres import PostgresStore

    return PostgresStore(DSN)


def test_migration_applied(migrated):
    # First run applies at least the init file on a fresh DB; on a reused DB it
    # may already be up to date. Either way the tables must exist.
    import psycopg

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from information_schema.tables where table_name in "
                    "('projects','scope_versions','scan_runs','findings','evidence','audit_events')")
        assert cur.fetchone()[0] == 6
        cur.execute("select relrowsecurity from pg_class where relname = 'evidence'")
        assert cur.fetchone()[0] is True


def test_store_roundtrip_and_org_scoping(store):
    import uuid

    pid = f"prj_{uuid.uuid4().hex[:12]}"
    row = store.insert("projects", {"id": pid, "organization_id": "org_a", "name": "A",
                                    "description": "", "extra": {"k": 1}})
    assert row["id"] == pid and row["extra"] == {"k": 1}        # data merged back
    assert store.get("projects", pid, organization_id="org_a")["name"] == "A"
    assert store.get("projects", pid, organization_id="org_b") is None  # AC 2
    assert store.update("projects", pid, organization_id="org_b", patch={"name": "X"}) is None
    upd = store.update("projects", pid, organization_id="org_a", patch={"name": "B"})
    assert upd["name"] == "B" and upd["extra"] == {"k": 1}
    assert any(p["id"] == pid for p in store.list("projects", organization_id="org_a"))


def test_audit_log_is_append_only(store):
    import uuid

    import psycopg

    aid = f"aud_{uuid.uuid4().hex[:12]}"
    store.insert("audit_events", {"id": aid, "organization_id": "org_a", "actor": "t",
                                  "action": "x", "at": "2026-01-01T00:00:00+00:00"})
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.RaiseException):
            cur.execute("delete from audit_events where id = %s", [aid])


def test_api_flow_on_postgres(migrated, monkeypatch):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setenv("DATABASE_URL", DSN)
    monkeypatch.setenv("PT_AUTO_MIGRATE", "1")
    from pt_agent.storage import reset_store_for_tests

    reset_store_for_tests()
    from fastapi.testclient import TestClient

    from pt_agent.api import app

    with TestClient(app) as client:
        assert client.get("/healthz").json()["storage"] == "postgres"
        # Real auth on Postgres: register, then use the bearer token.
        import uuid
        email = f"pg-{uuid.uuid4().hex[:8]}@example.test"
        reg = client.post("/auth/register-org", json={"organization_name": "PG Org", "email": email,
                                                      "password": "pg-password-123"})
        assert reg.status_code == 200, reg.text
        h = {"Authorization": f"Bearer {reg.json()['token']}"}
        assert client.get("/auth/me", headers=h).json()["user"]["email"] == email

        p = client.post("/projects", json={"name": "PG"}, headers=h).json()
        now = datetime.now(timezone.utc)
        a = client.post(f"/projects/{p['id']}/authorizations", json={
            "approver_name": "Dana", "approver_authority": "CISO",
            "valid_from": (now - timedelta(hours=1)).isoformat(),
            "valid_until": (now + timedelta(hours=2)).isoformat(), "control_verified": True}, headers=h).json()
        s = client.post(f"/projects/{p['id']}/scope-versions", json={
            "authorization_id": a["id"],
            "targets": [{"scheme": "https", "host": "app.test.example", "ports": [443]}],
            "allowed_modes": ["passive"]}, headers=h).json()
        ap = client.post(f"/scope-versions/{s['id']}/approve", headers=h).json()
        assert ap["status"] == "approved" and ap["targets"][0]["host"] == "app.test.example"
        run = client.post("/runs", json={"scope_version_id": s["id"], "mode": "passive"}, headers=h).json()
        ev = client.post("/evidence", json={"project_id": p["id"], "kind": "info_disclosure",
                                            "raw_snippet": "password=Hunter22 seen"}, headers=h).json()
        assert "Hunter22" not in ev["redacted_source"]
        # Cross-org read is a 404 even with the real id (AC 2): a second org.
        other = client.post("/auth/register-org", json={"organization_name": "Other", "email": f"o-{uuid.uuid4().hex[:8]}@example.test",
                                                        "password": "other-password-1"}).json()
        oh = {"Authorization": f"Bearer {other['token']}"}
        assert client.get(f"/evidence/{ev['id']}", headers=oh).status_code == 404
        f = client.post("/findings", json={
            "organization_id": "ignored", "project_id": p["id"], "run_id": run["id"],
            "title": "t", "asset_path": "/", "evidence_ids": [ev["id"]],
            "confidence": "verified", "proven_impact": "x",
        }, headers=h).json()
        rep = client.post("/reports", json={"run_id": run["id"]}, headers=h).json()
        assert f["id"] in rep["content"] and "Hunter22" not in rep["content"]
        assert client.get(f"/reports/{rep['id']}", headers=h).json()["id"] == rep["id"]
        stopped = client.post(f"/runs/{run['id']}/stop", headers=h).json()
        assert stopped["status"] == "stopped"
        events = client.get(f"/runs/{run['id']}/events", headers=h).json()["events"]
        assert any(e["action"] == "run.stop" for e in events)
        assert client.get("/dashboard", headers=h).json()["findings"]["total"] >= 1
    reset_store_for_tests()
