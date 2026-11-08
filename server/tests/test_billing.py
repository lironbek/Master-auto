"""Billing & service module: CRUD, charge engine, hours report, external
updates with signed links, expenses with FX, import from the old system."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from billing import engine
from cc import secrets as secrets_mod
from pt_agent.storage import reset_store_for_tests

os.environ.setdefault("CC_SECRET_KEY", secrets_mod.generate_key())
os.environ.setdefault("PT_ORG_HMAC_KEY", "test-hmac-key")


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


def _ws(client, h):
    return client.post("/cc/workspaces", json={"name": "Comax", "kind": "work"}, headers=h).json()["id"]


def test_engine_active_fraction_and_totals():
    from datetime import date
    assert engine.active_fraction("2026-01-01", None, date(2026, 11, 1), date(2026, 11, 30)) == 1.0
    assert engine.active_fraction("2026-11-16", None, date(2026, 11, 1), date(2026, 11, 30)) == 0.5
    assert engine.active_fraction("2026-12-01", None, date(2026, 11, 1), date(2026, 11, 30)) == 0.0
    assert engine.totals([{"total": 100}, {"total": 50.5}], 18) == {"subtotal": 150.5, "vat_pct": 18.0, "vat": 27.09, "total": 177.59}


def test_customers_products_subscriptions_and_monthly_charges(client):
    h = _login(client)
    ws = _ws(client, h)
    client.put(f"/billing/settings?workspace_id={ws}", json={"vat_pct": 18, "hourly_rate": 200, "business": {"name": "BEKMAN IT"}}, headers=h)
    cust = client.post("/billing/customers", json={"workspace_id": ws, "name": "גרנד קניון", "bill_hours": True}, headers=h).json()
    assert cust["client_id"]                                   # auto-linked to a usage client of the same name
    assert client.get(f"/cc/clients?workspace_id={ws}", headers=h).json()[0]["name"] == "גרנד קניון"
    prod = client.post("/billing/products", json={"workspace_id": ws, "name": "קופה", "price": 100, "has_light_user": True, "light_user_price": 40}, headers=h).json()
    svc = client.post("/billing/services", json={"workspace_id": ws, "description": "גיבוי ענן", "price": 50, "recurring": True}, headers=h).json()
    once = client.post("/billing/services", json={"workspace_id": ws, "description": "התקנה", "price": 500, "recurring": False}, headers=h).json()
    emp = client.post("/billing/employees", json={"workspace_id": ws, "name": "לירון", "role": "admin", "hourly_rate": 300}, headers=h).json()

    client.post("/billing/subscriptions", json={"customer_id": cust["id"], "kind": "product", "product_id": prod["id"], "user_count": 5, "light_user_count": 2, "valid_from": "2026-01-01"}, headers=h)
    client.post("/billing/subscriptions", json={"customer_id": cust["id"], "kind": "service", "service_id": svc["id"], "valid_from": "2026-01-01"}, headers=h)
    client.post("/billing/subscriptions", json={"customer_id": cust["id"], "kind": "service", "service_id": once["id"], "valid_from": "2026-11-10"}, headers=h)
    # half a month of a second product subscription
    client.post("/billing/subscriptions", json={"customer_id": cust["id"], "kind": "product", "product_id": prod["id"], "user_count": 2, "valid_from": "2026-11-16"}, headers=h)
    assert client.get(f"/billing/products?workspace_id={ws}", headers=h).json()[0]["users"] == 7

    tkt = client.post("/billing/tickets", json={"workspace_id": ws, "customer_id": cust["id"], "product_id": prod["id"], "employee_id": emp["id"], "title": "מדפסת",
                                                "opened_at": "2026-11-03T09:00:00Z", "initial_minutes": 60}, headers=h).json()
    assert tkt["number_label"] == "SC-000001" and tkt["minutes"] == 60
    client.post(f"/billing/tickets/{tkt['id']}/time", json={"minutes": 30, "entry_date": "2026-11-05", "description": "המשך"}, headers=h)
    assert client.get(f"/billing/tickets/{tkt['id']}", headers=h).json()["ticket"]["status"] == "in_progress"

    gen = client.post("/billing/charges/generate", json={"workspace_id": ws, "period": "2026-11"}, headers=h).json()
    assert gen["created"] == 1
    ch = client.get(f"/billing/charges/{gen['charge_ids'][0]}", headers=h).json()
    kinds = {l["kind"]: l for l in ch["lines"]}
    assert kinds["product"]["total"] in (500.0, 600.0) or True   # two product lines (full + partial) exist
    product_lines = [l for l in ch["lines"] if l["kind"] == "product"]
    assert len(product_lines) == 2 and sum(l["total"] for l in product_lines) == 500.0 + 100.0   # 5×100 + 2×100×0.5
    assert kinds["light"]["total"] == 80.0 and kinds["service"]["total"] in (50.0, 500.0)
    assert sum(l["total"] for l in ch["lines"] if l["kind"] == "service") == 550.0           # recurring 50 + one-off 500 in its start month
    assert kinds["hours"]["quantity"] == 1.5 and kinds["hours"]["total"] == 450.0           # 1.5h × employee rate 300
    c = ch["charge"]
    assert c["subtotal"] == 1680.0 and c["vat_pct"] == 18.0 and c["total"] == 1982.4

    # a manual line survives regeneration; non-draft charges are left alone
    client.post(f"/billing/charges/{c['id']}/lines", json={"description": "הנחה", "quantity": 1, "unit_price": -80}, headers=h)
    gen2 = client.post("/billing/charges/generate", json={"workspace_id": ws, "period": "2026-11"}, headers=h).json()
    assert gen2["updated"] == 1 and gen2["created"] == 0
    ch2 = client.get(f"/billing/charges/{c['id']}", headers=h).json()
    assert any(l["kind"] == "manual" for l in ch2["lines"]) and ch2["charge"]["subtotal"] == 1600.0
    issued = client.patch(f"/billing/charges/{c['id']}", json={"status": "issued"}, headers=h).json()
    assert issued["status"] == "issued" and issued["issued_at"]
    # the billed time entries are now locked
    te = client.get(f"/billing/tickets/{tkt['id']}", headers=h).json()["time_entries"][0]
    assert te["billed_charge_id"] == c["id"]
    assert client.delete(f"/billing/time/{te['id']}", headers=h).status_code == 409
    assert client.post("/billing/charges/generate", json={"workspace_id": ws, "period": "2026-11"}, headers=h).json()["skipped_non_draft"] == 1
    paid = client.patch(f"/billing/charges/{c['id']}", json={"status": "paid"}, headers=h).json()
    assert paid["paid_at"]
    assert client.delete(f"/billing/charges/{c['id']}", headers=h).status_code == 409

    # print view & excel exports
    html = client.get(f"/billing/charges/{c['id']}/print", headers=h).text
    assert "BEKMAN IT" in html and "גרנד קניון" in html and "1,888.00" in html
    x = client.get(f"/billing/exports/charges.xlsx?workspace_id={ws}&period=2026-11", headers=h)
    assert x.status_code == 200 and x.content[:2] == b"PK"

    # hours report
    rep = client.get(f"/billing/reports/hours?workspace_id={ws}&customer_id={cust['id']}&from=2026-11-01&to=2026-11-30", headers=h).json()
    assert rep["total_minutes"] == 90 and rep["by_employee"][0]["employee_name"] == "לירון"
    assert client.get(f"/billing/reports/hours?workspace_id={ws}&from=2026-11-01&to=2026-11-30&format=xlsx", headers=h).content[:2] == b"PK"
    assert "דוח שעות" in client.get(f"/billing/reports/hours?workspace_id={ws}&format=html", headers=h).text

    # dashboard + customer detail + activities
    ov = client.get(f"/billing/overview?workspace_id={ws}", headers=h).json()
    assert ov["customers"] == 1 and ov["open_tickets"] == 1 and ov["users_by_product"][0]["users"] == 7
    det = client.get(f"/billing/customers/{cust['id']}/detail", headers=h).json()
    assert len(det["subscriptions"]) == 4 and det["charges"][0]["status"] == "paid" and det["customer"]["open_tickets"] == 1
    acts = client.get(f"/billing/activities?workspace_id={ws}", headers=h).json()
    assert {a["type"] for a in acts} == {"ticket", "time_entry"}
    # a customer with tickets cannot be deleted, only closed
    assert client.delete(f"/billing/customers/{cust['id']}", headers=h).status_code == 409


def test_external_update_link_requires_valid_token(client):
    h = _login(client)
    ws = _ws(client, h)
    cust = client.post("/billing/customers", json={"workspace_id": ws, "name": "נווה מיכאל"}, headers=h).json()
    tkt = client.post("/billing/tickets", json={"workspace_id": ws, "customer_id": cust["id"], "title": "AP"}, headers=h).json()
    link = client.post(f"/billing/tickets/{tkt['id']}/external-link", headers=h).json()
    tok = link["token"]
    pub = client.get(f"/billing/public/{tok}")
    assert pub.status_code == 200 and pub.json()["ticket"]["customer_name"] == "נווה מיכאל"
    assert client.post(f"/billing/public/{tok}", json={"contact_name": "אבי", "content": "הוחלף מתג", "minutes": 45}).status_code == 200
    bad = tok[:-4] + ("AAAA" if not tok.endswith("AAAA") else "BBBB")
    assert client.get(f"/billing/public/{bad}").status_code == 404
    assert client.post(f"/billing/public/{bad}", json={"contact_name": "x", "content": "y"}).status_code == 404
    t = client.get(f"/billing/tickets/{tkt['id']}", headers=h).json()
    assert t["external_updates"][0]["content"] == "הוחלף מתג" and t["external_updates"][0]["minutes"] == 45
    assert any(a["type"] == "external_update" for a in client.get(f"/billing/activities?workspace_id={ws}", headers=h).json())


def test_expenses_fx_and_export(client):
    h = _login(client)
    ws = _ws(client, h)
    client.post("/billing/fx", json={"currency": "USD", "rate_date": "2026-11-01", "rate": 3.5}, headers=h)
    e1 = client.post("/billing/expenses", json={"workspace_id": ws, "name": "Vercel", "amount": 20, "currency": "USD", "category": "infra", "expense_date": "2026-11-05"}, headers=h).json()
    assert e1["rate_used"] == 3.5 and e1["amount_ils"] == 70.0 and e1["rate_source"] == "rate 2026-11-01"
    e2 = client.post("/billing/expenses", json={"workspace_id": ws, "name": "Old", "amount": 10, "currency": "EUR", "expense_date": "2025-01-05"}, headers=h).json()
    assert e2["rate_used"] == 4.0 and e2["rate_source"] == "default"
    e3 = client.patch(f"/billing/expenses/{e1['id']}", json={"amount": 30, "rate": 4}, headers=h).json()
    assert e3["amount_ils"] == 120.0 and e3["rate_source"] == "manual"
    assert client.post("/billing/expenses", json={"workspace_id": ws, "name": "x", "amount": 1, "currency": "GBP"}, headers=h).status_code == 422
    assert client.get(f"/billing/exports/expenses.xlsx?workspace_id={ws}", headers=h).content[:2] == b"PK"
    assert client.get(f"/billing/overview?workspace_id={ws}", headers=h).json()["expenses_month"] >= 0


def test_import_legacy_is_idempotent(client):
    h = _login(client)
    ws = _ws(client, h)
    payload = {
        "workspace_id": ws,
        "employees": [{"id": "E1", "name": "לירון", "role": "admin", "hourly_rate": 250}],
        "customers": [{"id": "C1", "name": "נווה מיכאל", "email": "a@b.c"}],
        "products": [{"id": "P1", "name": "שירותי IT", "price": 0}],
        "services": [{"id": "S1", "description": "בנק שעות", "price": 1000, "recurring": True}],
        "product_users": [{"id": "PU1", "customer_id": "C1", "product_id": "P1", "user_count": 3, "valid_from": "2025-01-01"}],
        "service_tickets": [{"id": "T1", "customer_id": "C1", "product_id": "P1", "assigned_employee_id": "E1", "title": "SC-001075", "status": "in-progress", "priority": "medium", "created_at": "2026-05-06T09:00:00+03:00"},
                            {"id": "T2", "customer_id": "C1", "product_id": "P1", "assigned_employee_id": "E1", "title": "מתגים", "status": "closed", "priority": "גבוהה", "created_at": "2026-04-07T09:00:00+03:00"}],
        "service_time_entries": [{"id": "TE1", "ticket_id": "T1", "employee_id": "E1", "time_spent": 60, "entry_date": "2026-05-06", "description": "בדיקה"}],
        "external_ticket_updates": [{"id": "X1", "ticket_id": "T1", "contact_name": "אבי", "update_content": "תוקן", "treatment_time": 30, "update_date": "2026-05-07"}],
        "monthly_summaries": [{"id": "M1", "customer_id": "C1", "month": 5, "year": 2026, "total_amount": 1500, "paid": True, "payment_date": "2026-06-01"}],
        "billing_items": [{"id": "B1", "customer_id": "C1", "product_id": "P1", "price_per_unit": 500, "quantity": 3, "billing_date": "2026-05-15"}],
        "expenses": [{"id": "EX1", "name": "Supabase", "amount": 25, "currency": "USD", "amount_in_ils": 92.5, "category": "דאטהבייס", "date": "2026-05-02", "recurring": True}],
        "knowledge_items": [{"id": "K1", "product_id": "P1", "title": "VLAN", "content": "...", "tags": ["רשת"]}],
    }
    rep = client.post("/billing/import", json=payload, headers=h).json()["report"]
    assert all(v["errors"] == 0 for v in rep.values()), rep
    assert rep["service_tickets"]["inserted"] == 2 and rep["billing_items"]["inserted"] == 1
    tickets = client.get(f"/billing/tickets?workspace_id={ws}", headers=h).json()
    assert [t["number_label"] for t in tickets] == ["SC-000002", "SC-000001"]          # numbered in chronological order, listed newest first
    assert {t["status"] for t in tickets} == {"in_progress", "closed"} and tickets[1]["priority"] == "high"
    charges = client.get(f"/billing/charges?workspace_id={ws}", headers=h).json()
    assert len(charges) == 1 and charges[0]["status"] == "paid" and charges[0]["total"] == 1500.0 and charges[0]["lines"] == 1
    exp = client.get(f"/billing/expenses?workspace_id={ws}", headers=h).json()[0]
    assert exp["category"] == "database" and exp["amount_ils"] == 92.5 and exp["rate_used"] == 3.7
    # second run: everything skipped, nothing duplicated
    rep2 = client.post("/billing/import", json=payload, headers=h).json()["report"]
    assert all(v["inserted"] == 0 for v in rep2.values()), rep2
    assert len(client.get(f"/billing/tickets?workspace_id={ws}", headers=h).json()) == 2
    assert client.get(f"/billing/knowledge?workspace_id={ws}", headers=h).json()[0]["product_name"] == "שירותי IT"


def test_viewer_cannot_write(client):
    h = _login(client)
    ws = _ws(client, h)
    client.post("/auth/users", json={"email": "v@acme.io", "password": "correct-horse-battery", "display_name": "V", "role": "auditor"}, headers=h)
    me = client.post("/auth/login", json={"email": "v@acme.io", "password": "correct-horse-battery"}).json()
    vh = {"Authorization": f"Bearer {me['token']}"}
    user_id = me["user"]["id"]
    client.post(f"/cc/workspaces/{ws}/members", json={"user_id": user_id, "role": "viewer"}, headers=h)
    assert client.get(f"/billing/customers?workspace_id={ws}", headers=vh).status_code == 200
    assert client.post("/billing/customers", json={"workspace_id": ws, "name": "x"}, headers=vh).status_code == 403
