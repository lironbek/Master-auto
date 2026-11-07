"""Usage metering per client: reporter ingestion, de-duplication, aggregation,
project/client linkage and agent-run metering."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from cc import secrets as secrets_mod
from pt_agent.storage import reset_store_for_tests

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


def _setup(client, h):
    ws = client.post("/cc/workspaces", json={"name": "W", "kind": "work"}, headers=h).json()
    tok = client.post(f"/cc/workspaces/{ws['id']}/report-token", headers=h).json()["report_token"]
    return ws, {"X-Report-Token": tok}


def test_usage_report_by_client_provider_and_interface(client):
    h = _login(client)
    ws, th = _setup(client, h)
    body = {"workspace_id": ws["id"], "entries": [
        {"provider": "whatsapp", "metric": "messages", "quantity": 12, "recipients": 5, "interface": "n8n/orders-bot", "client": "לקוח א", "external_id": "wa-1",
         "occurred_at": "2026-11-07T10:00:00+00:00"},
        {"provider": "gemini", "metric": "requests", "quantity": 30, "interface": "n8n/orders-bot", "client": "לקוח א", "external_id": "gm-1", "model": "gemini-2.5-pro"},
        {"provider": "claude", "metric": "tokens_in", "quantity": 1200, "interface": "app/crm", "client": "לקוח ב", "external_id": "cl-1"},
        {"provider": "ocr", "metric": "pages", "quantity": 40, "interface": "app/crm", "client": "לקוח ב", "external_id": "ocr-1"},
    ]}
    r = client.post("/cc/usage", json=body, headers=th)
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 4 and r.json()["duplicates"] == 0 and len(r.json()["clients_created"]) == 2

    # Replay is recognised as duplicate; recipients were recorded as their own metric.
    r2 = client.post("/cc/usage", json=body, headers=th).json()
    assert r2["accepted"] == 0 and r2["duplicates"] == 4

    rep = client.get(f"/cc/usage?workspace_id={ws['id']}", headers=h).json()
    assert rep["totals"] == {"messages": 12, "recipients": 5, "requests": 30, "tokens_in": 1200, "pages": 40}
    by_client = {c["client_name"]: c for c in rep["by_client"]}
    assert by_client["לקוח א"]["metrics"] == {"messages": 12, "recipients": 5, "requests": 30}
    assert by_client["לקוח א"]["providers"]["whatsapp"] == {"messages": 12, "recipients": 5}
    assert by_client["לקוח ב"]["providers"]["ocr"] == {"pages": 40}
    ifaces = {(i["interface"], i["provider"]): i["metrics"] for i in rep["by_interface"]}
    assert ifaces[("n8n/orders-bot", "gemini")] == {"requests": 30}
    assert rep["entries"][0]["client_name"] in ("לקוח א", "לקוח ב")

    # Filters: by client and by provider.
    a = by_client["לקוח א"]["client_id"]
    only_a = client.get(f"/cc/usage?workspace_id={ws['id']}&client_id={a}", headers=h).json()
    assert set(only_a["totals"]) == {"messages", "recipients", "requests"}
    only_ocr = client.get(f"/cc/usage?workspace_id={ws['id']}&provider=ocr", headers=h).json()
    assert only_ocr["totals"] == {"pages": 40}

    # Clients are listed with their projects once assigned.
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "CRM", "client_id": a}, headers=h).json()
    clients = client.get(f"/cc/clients?workspace_id={ws['id']}", headers=h).json()
    assert [c["projects"] for c in clients if c["id"] == a] == [[{"id": pr["id"], "name": "CRM"}]]


def test_usage_bad_token_metric_and_cross_workspace_client(client):
    h = _login(client)
    ws, th = _setup(client, h)
    bad = {"workspace_id": ws["id"], "entries": [{"provider": "claude", "metric": "calls", "quantity": 1}]}
    assert client.post("/cc/usage", json=bad, headers=th).status_code == 422
    ok = {"workspace_id": ws["id"], "entries": [{"provider": "claude", "metric": "requests", "quantity": 1}]}
    assert client.post("/cc/usage", json=ok, headers={"X-Report-Token": "nope"}).status_code == 401
    ws2 = client.post("/cc/workspaces", json={"name": "W2"}, headers=h).json()
    c2 = client.post("/cc/clients", json={"workspace_id": ws2["id"], "name": "Other"}, headers=h).json()
    assert client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "P", "client_id": c2["id"]}, headers=h).status_code == 422
    assert client.post("/cc/clients", json={"workspace_id": ws2["id"], "name": "other"}, headers=h).status_code == 409


def test_project_usage_defaults_to_its_client_and_agent_runs_are_metered(client, monkeypatch):
    h = _login(client)
    ws, th = _setup(client, h)
    c = client.post("/cc/clients", json={"workspace_id": ws["id"], "name": "Beta"}, headers=h).json()
    pr = client.post("/cc/projects", json={"workspace_id": ws["id"], "name": "P", "client_id": c["id"]}, headers=h).json()
    client.post("/cc/usage", json={"workspace_id": ws["id"], "entries": [
        {"provider": "gemini", "metric": "requests", "quantity": 3, "project_id": pr["id"], "interface": "app/p"}]}, headers=th)
    # Agent run with a (fake) model call records requests + tokens for the project's client.
    import cc.agents as agents
    monkeypatch.setattr(agents, "_resolve_key", lambda store, org, agent: ("sk-fake", None))
    monkeypatch.setattr(agents, "claude_summary", lambda key, model, instr, ctx: ("summary", {"input": 500, "output": 80}))
    a = client.post("/cc/agents", json={"workspace_id": ws["id"], "name": "Reporter"}, headers=h).json()
    run = client.post(f"/cc/agents/{a['id']}/runs", json={"project_id": pr["id"]}, headers=h).json()
    assert run["status"] == "completed"
    rep = client.get(f"/cc/usage?workspace_id={ws['id']}&client_id={c['id']}", headers=h).json()
    assert rep["totals"] == {"requests": 4, "tokens_in": 500, "tokens_out": 80}
    assert {i["interface"] for i in rep["by_interface"]} == {"app/p", "agent:Reporter"}
    detail = client.get(f"/cc/projects/{pr['id']}", headers=h).json()
    assert detail["client"]["name"] == "Beta" and detail["usage_month"]["totals"]["tokens_in"] == 500
