"""HTTP API of the billing & service module (prefix /billing).

Permissions follow the control center: a workspace editor manages data, a
viewer reads, an admin changes settings. The external-update endpoints are the
only unauthenticated ones and require a signed, expiring token.
"""

import os
from datetime import date
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from cc import usage as usage_engine
from cc.service import (
    WS_ADMIN,
    WS_EDITOR,
    audit,
    get_in_workspace,
    iso,
    list_in_workspaces,
    new_id,
    now,
    parse_dt,
    require_workspace,
    visible_workspace_ids,
)
from pt_agent.api.auth import Principal, current_principal
from pt_agent.storage import get_store

from . import engine, exports, legacy
from .models import (
    CHARGE_STATUS,
    CURRENCIES,
    CUSTOMER_STATUS,
    EMPLOYEE_ROLE,
    EXPENSE_CATEGORY,
    LINE_KIND,
    SUBSCRIPTION_KIND,
    TICKET_PRIORITY,
    TICKET_STATUS,
    ChargeLineIn,
    ChargePatch,
    CustomerIn,
    CustomerPatch,
    EmployeeIn,
    EmployeePatch,
    ExpenseIn,
    ExpensePatch,
    ExternalUpdateIn,
    FxRateIn,
    GenerateIn,
    ImportIn,
    KnowledgeIn,
    KnowledgePatch,
    LegacySupabaseIn,
    ManualChargeIn,
    ProductIn,
    ProductPatch,
    ServiceIn,
    ServicePatch,
    SettingsIn,
    SubscriptionIn,
    SubscriptionPatch,
    TicketIn,
    TicketPatch,
    TimeEntryIn,
    TimeEntryPatch,
)

router = APIRouter(prefix="/billing", tags=["billing"])
Row = dict[str, Any]


def _store():
    return get_store()


def _enum(value: Optional[str], allowed: tuple, field: str) -> None:
    if value is not None and value not in allowed:
        raise HTTPException(status_code=422, detail=f"{field} must be one of {', '.join(allowed)}")


def _date(v: Optional[str], default: Optional[date] = None) -> Optional[str]:
    if v in (None, ""):
        return default.isoformat() if default else None
    d = engine.to_date(v)
    if d is None:
        raise HTTPException(status_code=422, detail=f"invalid date: {v}")
    return d.isoformat()


def _ref(p: Principal, table: str, row_id: Optional[str], ws: str, label: str) -> Optional[Row]:
    """A referenced row must exist in the same workspace."""
    if not row_id:
        return None
    row = _store().get(table, row_id, organization_id=p.organization_id)
    if not row or row.get("workspace_id") != ws:
        raise HTTPException(status_code=422, detail=f"{label} not found in workspace")
    return row


def _names(p: Principal, table: str, ws_ids: list[str], key: str = "name") -> dict[str, str]:
    out: dict[str, str] = {}
    for ws in ws_ids:
        for r in _store().list(table, organization_id=p.organization_id, workspace_id=ws):
            out[r["id"]] = r.get(key, "")
    return out


# --- generic CRUD -------------------------------------------------------------

def _crud(name: str, table: str, prefix: str, InModel: type[BaseModel], PatchModel: type[BaseModel], *,
          prepare: Optional[Callable[[Principal, Row, Optional[Row]], None]] = None,
          enrich: Optional[Callable[[Principal, list[Row]], list[Row]]] = None,
          before_delete: Optional[Callable[[Principal, Row], None]] = None,
          list_filters: tuple[str, ...] = ()) -> None:
    """Register list / create / read / update / delete for a workspace-scoped table."""

    def _list(workspace_id: Optional[str] = None, p: Principal = Depends(current_principal)):
        rows = list_in_workspaces(p, table, workspace_id)
        return enrich(p, rows) if enrich else rows

    def _create(body: InModel, p: Principal = Depends(current_principal)):  # type: ignore[valid-type]
        data = body.model_dump()
        require_workspace(p, data["workspace_id"], WS_EDITOR)
        row = {"id": new_id(prefix), "organization_id": p.organization_id, "created_at": iso(), **data}
        if prepare:
            prepare(p, row, None)
        row = _store().insert(table, row)
        audit(p, f"billing.{name}.create", detail=row["id"])
        return (enrich(p, [row]) if enrich else [row])[0]

    def _read(row_id: str, p: Principal = Depends(current_principal)):
        row = get_in_workspace(p, table, row_id)
        return (enrich(p, [row]) if enrich else [row])[0]

    def _update(row_id: str, body: PatchModel, p: Principal = Depends(current_principal)):  # type: ignore[valid-type]
        current = get_in_workspace(p, table, row_id, minimum=WS_EDITOR)
        patch = {k: v for k, v in body.model_dump().items() if v is not None}
        merged = {**current, **patch}
        if prepare:
            prepare(p, merged, current)
        row = _store().update(table, row_id, organization_id=p.organization_id, patch={k: merged[k] for k in merged if k not in ("id", "organization_id", "created_at")})
        audit(p, f"billing.{name}.update", detail=f"{row_id} {','.join(patch)}")
        return (enrich(p, [row]) if enrich else [row])[0]

    def _delete(row_id: str, p: Principal = Depends(current_principal)):
        row = get_in_workspace(p, table, row_id, minimum=WS_EDITOR)
        if before_delete:
            before_delete(p, row)
        _store().delete(table, row_id, organization_id=p.organization_id)
        audit(p, f"billing.{name}.delete", detail=row_id)
        return {"ok": True}

    router.add_api_route(f"/{name}", _list, methods=["GET"], name=f"list_{name}")
    router.add_api_route(f"/{name}", _create, methods=["POST"], name=f"create_{name}")
    router.add_api_route(f"/{name}/{{row_id}}", _read, methods=["GET"], name=f"read_{name}")
    router.add_api_route(f"/{name}/{{row_id}}", _update, methods=["PATCH"], name=f"update_{name}")
    router.add_api_route(f"/{name}/{{row_id}}", _delete, methods=["DELETE"], name=f"delete_{name}")


# --- customers ----------------------------------------------------------------

def _prep_customer(p: Principal, row: Row, current: Optional[Row]) -> None:
    _enum(row.get("status"), CUSTOMER_STATUS, "status")
    ws = row["workspace_id"]
    if row.get("client_id") == "":
        row["client_id"] = None
    elif row.get("client_id"):
        _ref(p, "clients", row["client_id"], ws, "client")
    elif current is None:
        # default: the billing customer is also the usage-metering client of the same name
        created: list[str] = []
        row["client_id"] = usage_engine.resolve_client(_store(), p.organization_id, ws, client_id=None, name=row["name"], created=created, source="billing")


def _customer_stats(p: Principal, rows: list[Row]) -> list[Row]:
    if not rows:
        return rows
    ws_ids = sorted({r["workspace_id"] for r in rows})
    subs: dict[str, list[Row]] = {}
    tickets: dict[str, list[Row]] = {}
    charges: dict[str, list[Row]] = {}
    for ws in ws_ids:
        for s in _store().list("bl_subscriptions", organization_id=p.organization_id, workspace_id=ws):
            subs.setdefault(s["customer_id"], []).append(s)
        for t in _store().list("bl_tickets", organization_id=p.organization_id, workspace_id=ws):
            tickets.setdefault(t["customer_id"], []).append(t)
        for c in _store().list("bl_charges", organization_id=p.organization_id, workspace_id=ws):
            charges.setdefault(c["customer_id"], []).append(c)
    out = []
    for r in rows:
        s = [x for x in subs.get(r["id"], []) if not x.get("valid_until") or engine.to_date(x["valid_until"]) >= now().date()]
        out.append({**r, "users": sum(int(x.get("user_count") or 0) for x in s if x.get("kind", "product") == "product"),
                    "subscriptions": len(s), "open_tickets": sum(1 for t in tickets.get(r["id"], []) if t.get("status") in ("open", "in_progress")),
                    "unpaid": engine.money(sum(engine.money(c.get("total")) for c in charges.get(r["id"], []) if c.get("status") == "issued"))})
    return out


def _customer_guard(p: Principal, row: Row) -> None:
    org = p.organization_id
    n_t = len(_store().list("bl_tickets", organization_id=org, customer_id=row["id"]))
    n_c = len(_store().list("bl_charges", organization_id=org, customer_id=row["id"]))
    if n_t or n_c:
        raise HTTPException(status_code=409, detail=f"ללקוח יש {n_t} קריאות ו-{n_c} חיובים. סמן אותו כסגור במקום למחוק.")
    for s in _store().list("bl_subscriptions", organization_id=org, customer_id=row["id"]):
        _store().delete("bl_subscriptions", s["id"], organization_id=org)


_crud("customers", "bl_customers", "cus", CustomerIn, CustomerPatch, prepare=_prep_customer, enrich=_customer_stats, before_delete=_customer_guard)


@router.get("/customers/{row_id}/detail")
def customer_detail(row_id: str, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    c = get_in_workspace(p, "bl_customers", row_id)
    ws = c["workspace_id"]
    products = _names(p, "bl_products", [ws])
    services = _names(p, "bl_services", [ws], "description")
    employees = _names(p, "bl_employees", [ws])
    subs = [{**s, "product_name": products.get(s.get("product_id") or "", ""), "service_name": services.get(s.get("service_id") or "", "")}
            for s in store.list("bl_subscriptions", organization_id=org, customer_id=row_id)]
    tickets = sorted(store.list("bl_tickets", organization_id=org, customer_id=row_id), key=lambda t: str(t.get("opened_at")), reverse=True)
    tickets = [{**t, "employee_name": employees.get(t.get("employee_id") or "", "")} for t in tickets[:100]]
    charges = sorted(store.list("bl_charges", organization_id=org, customer_id=row_id), key=lambda x: x.get("period", ""), reverse=True)
    today = now().date()
    hours = engine.hours_report(store, org, ws, customer_id=row_id, start=today.replace(day=1), end=today)
    usage = None
    if c.get("client_id"):
        start, end = usage_engine.window(None, None)
        rows = usage_engine.filter_entries(store.list("usage_entries", organization_id=org, client_id=c["client_id"]),
                                           start=start, end=end, client_id=None, project_id=None, provider=None, interface=None)
        u = usage_engine.summarize(rows, {}, {})
        usage = {"totals": u["totals"], "by_provider": u["by_provider"]}
    return {"customer": _customer_stats(p, [c])[0], "subscriptions": subs, "tickets": tickets, "charges": charges,
            "hours_month": hours["total_minutes"], "usage_month": usage}


# --- products / services / employees -----------------------------------------

def _prep_product(p: Principal, row: Row, current: Optional[Row]) -> None:
    if row.get("project_id") == "":
        row["project_id"] = None
    elif row.get("project_id"):
        pr = _store().get("cc_projects", row["project_id"], organization_id=p.organization_id)
        if not pr:
            raise HTTPException(status_code=422, detail="project not found")


def _product_stats(p: Principal, rows: list[Row]) -> list[Row]:
    if not rows:
        return rows
    counts: dict[str, dict[str, int]] = {}
    for ws in sorted({r["workspace_id"] for r in rows}):
        for s in _store().list("bl_subscriptions", organization_id=p.organization_id, workspace_id=ws):
            if s.get("kind", "product") != "product" or (s.get("valid_until") and engine.to_date(s["valid_until"]) < now().date()):
                continue
            b = counts.setdefault(s.get("product_id") or "", {"customers": 0, "users": 0, "light": 0})
            b["customers"] += 1
            b["users"] += int(s.get("user_count") or 0)
            b["light"] += int(s.get("light_user_count") or 0)
    return [{**r, **counts.get(r["id"], {"customers": 0, "users": 0, "light": 0})} for r in rows]


def _product_guard(p: Principal, row: Row) -> None:
    if _store().list("bl_subscriptions", organization_id=p.organization_id, product_id=row["id"]):
        raise HTTPException(status_code=409, detail="המוצר משויך ללקוחות. הסר את המנויים קודם.")


_crud("products", "bl_products", "prd", ProductIn, ProductPatch, prepare=_prep_product, enrich=_product_stats, before_delete=_product_guard)


def _service_guard(p: Principal, row: Row) -> None:
    if _store().list("bl_subscriptions", organization_id=p.organization_id, service_id=row["id"]):
        raise HTTPException(status_code=409, detail="השירות משויך ללקוחות. הסר את המנויים קודם.")


_crud("services", "bl_services", "svc", ServiceIn, ServicePatch, before_delete=_service_guard)


def _prep_employee(p: Principal, row: Row, current: Optional[Row]) -> None:
    _enum(row.get("role"), EMPLOYEE_ROLE, "role")
    if row.get("user_id") == "":
        row["user_id"] = None
    elif row.get("user_id") and not _store().get("users", row["user_id"], organization_id=p.organization_id):
        raise HTTPException(status_code=422, detail="user not found")


def _employee_stats(p: Principal, rows: list[Row]) -> list[Row]:
    if not rows:
        return rows
    users = {u["id"]: u for u in _store().list("users", organization_id=p.organization_id)}
    month = now().strftime("%Y-%m")
    minutes: dict[str, int] = {}
    open_t: dict[str, int] = {}
    for ws in sorted({r["workspace_id"] for r in rows}):
        for te in _store().list("bl_time_entries", organization_id=p.organization_id, workspace_id=ws):
            if str(te.get("entry_date", ""))[:7] == month:
                minutes[te.get("employee_id") or ""] = minutes.get(te.get("employee_id") or "", 0) + int(te.get("minutes") or 0)
        for t in _store().list("bl_tickets", organization_id=p.organization_id, workspace_id=ws):
            if t.get("status") in ("open", "in_progress"):
                open_t[t.get("employee_id") or ""] = open_t.get(t.get("employee_id") or "", 0) + 1
    return [{**r, "user_email": users.get(r.get("user_id") or "", {}).get("email", ""), "minutes_month": minutes.get(r["id"], 0), "open_tickets": open_t.get(r["id"], 0)} for r in rows]


_crud("employees", "bl_employees", "emp", EmployeeIn, EmployeePatch, prepare=_prep_employee, enrich=_employee_stats)


# --- subscriptions ------------------------------------------------------------

@router.get("/subscriptions")
def list_subscriptions(workspace_id: Optional[str] = None, customer_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    rows = list_in_workspaces(p, "bl_subscriptions", workspace_id)
    if customer_id:
        rows = [r for r in rows if r["customer_id"] == customer_id]
    ws_ids = sorted({r["workspace_id"] for r in rows})
    products, services, customers = _names(p, "bl_products", ws_ids), _names(p, "bl_services", ws_ids, "description"), _names(p, "bl_customers", ws_ids)
    return [{**r, "product_name": products.get(r.get("product_id") or "", ""), "service_name": services.get(r.get("service_id") or "", ""),
             "customer_name": customers.get(r["customer_id"], "")} for r in rows]


@router.post("/subscriptions")
def create_subscription(body: SubscriptionIn, p: Principal = Depends(current_principal)):
    c = get_in_workspace(p, "bl_customers", body.customer_id, minimum=WS_EDITOR)
    _enum(body.kind, SUBSCRIPTION_KIND, "kind")
    if body.kind == "product":
        _ref(p, "bl_products", body.product_id, c["workspace_id"], "product")
        if not body.product_id:
            raise HTTPException(status_code=422, detail="product_id required")
    else:
        _ref(p, "bl_services", body.service_id, c["workspace_id"], "service")
        if not body.service_id:
            raise HTTPException(status_code=422, detail="service_id required")
    row = {"id": new_id("sub"), "organization_id": p.organization_id, "workspace_id": c["workspace_id"], "created_at": iso(), **body.model_dump(),
           "valid_from": _date(body.valid_from, now().date()), "valid_until": _date(body.valid_until)}
    row = _store().insert("bl_subscriptions", row)
    audit(p, "billing.subscription.create", detail=f"{row['id']} {body.customer_id}")
    return row


@router.patch("/subscriptions/{row_id}")
def update_subscription(row_id: str, body: SubscriptionPatch, p: Principal = Depends(current_principal)):
    get_in_workspace(p, "bl_subscriptions", row_id, minimum=WS_EDITOR)
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "valid_from" in patch:
        patch["valid_from"] = _date(patch["valid_from"], now().date())
    if "valid_until" in patch:
        patch["valid_until"] = _date(patch["valid_until"])
    row = _store().update("bl_subscriptions", row_id, organization_id=p.organization_id, patch=patch)
    audit(p, "billing.subscription.update", detail=row_id)
    return row


@router.delete("/subscriptions/{row_id}")
def delete_subscription(row_id: str, p: Principal = Depends(current_principal)):
    get_in_workspace(p, "bl_subscriptions", row_id, minimum=WS_EDITOR)
    _store().delete("bl_subscriptions", row_id, organization_id=p.organization_id)
    audit(p, "billing.subscription.delete", detail=row_id)
    return {"ok": True}


# --- tickets & time -----------------------------------------------------------

def _next_number(p: Principal, ws: str) -> int:
    return max([int(t.get("number") or 0) for t in _store().list("bl_tickets", organization_id=p.organization_id, workspace_id=ws)] + [0]) + 1


def _ticket_view(p: Principal, rows: list[Row]) -> list[Row]:
    if not rows:
        return rows
    ws_ids = sorted({r["workspace_id"] for r in rows})
    customers, products, employees = _names(p, "bl_customers", ws_ids), _names(p, "bl_products", ws_ids), _names(p, "bl_employees", ws_ids)
    minutes: dict[str, int] = {}
    for ws in ws_ids:
        for te in _store().list("bl_time_entries", organization_id=p.organization_id, workspace_id=ws):
            minutes[te["ticket_id"]] = minutes.get(te["ticket_id"], 0) + int(te.get("minutes") or 0)
    prefix = {ws: engine.settings_for(_store(), p.organization_id, ws).get("ticket_prefix", "SC") for ws in ws_ids}
    return [{**r, "number_label": engine.ticket_number(prefix[r["workspace_id"]], int(r.get("number") or 0)), "customer_name": customers.get(r["customer_id"], ""),
             "product_name": products.get(r.get("product_id") or "", ""), "employee_name": employees.get(r.get("employee_id") or "", ""),
             "minutes": minutes.get(r["id"], 0)} for r in rows]


@router.get("/tickets")
def list_tickets(workspace_id: Optional[str] = None, status: Optional[str] = None, customer_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    rows = list_in_workspaces(p, "bl_tickets", workspace_id)
    if status == "active":
        rows = [r for r in rows if r.get("status") in ("open", "in_progress")]
    elif status:
        rows = [r for r in rows if r.get("status") == status]
    if customer_id:
        rows = [r for r in rows if r["customer_id"] == customer_id]
    rows.sort(key=lambda r: str(r.get("opened_at")), reverse=True)
    return _ticket_view(p, rows)


@router.post("/tickets")
def create_ticket(body: TicketIn, p: Principal = Depends(current_principal)):
    ws = body.workspace_id
    require_workspace(p, ws, WS_EDITOR)
    _enum(body.status, TICKET_STATUS, "status")
    _enum(body.priority, TICKET_PRIORITY, "priority")
    _ref(p, "bl_customers", body.customer_id, ws, "customer")
    _ref(p, "bl_products", body.product_id, ws, "product")
    _ref(p, "bl_employees", body.employee_id, ws, "employee")
    opened = parse_dt(body.opened_at) if body.opened_at else now()
    if opened is None:
        raise HTTPException(status_code=422, detail="invalid opened_at")
    data = body.model_dump(exclude={"initial_minutes", "initial_note"})
    row = _store().insert("bl_tickets", {"id": new_id("tkt"), "organization_id": p.organization_id, "created_at": iso(), **data,
                                         "number": _next_number(p, ws), "opened_at": iso(opened),
                                         "closed_at": iso() if body.status in ("resolved", "closed") else None})
    if body.initial_minutes:
        _store().insert("bl_time_entries", {"id": new_id("tme"), "organization_id": p.organization_id, "workspace_id": ws, "ticket_id": row["id"],
                                            "employee_id": body.employee_id, "description": body.initial_note or "זמן ראשוני בפתיחת הקריאה",
                                            "minutes": body.initial_minutes, "entry_date": opened.date().isoformat(), "created_at": iso()})
    audit(p, "billing.ticket.create", detail=row["id"])
    return _ticket_view(p, [row])[0]


@router.get("/tickets/{row_id}")
def get_ticket(row_id: str, p: Principal = Depends(current_principal)):
    t = get_in_workspace(p, "bl_tickets", row_id)
    employees = _names(p, "bl_employees", [t["workspace_id"]])
    entries = sorted(_store().list("bl_time_entries", organization_id=p.organization_id, ticket_id=row_id), key=lambda e: (str(e.get("entry_date")), str(e.get("created_at"))), reverse=True)
    updates = sorted(_store().list("bl_external_updates", organization_id=p.organization_id, ticket_id=row_id), key=lambda e: str(e.get("created_at")), reverse=True)
    return {"ticket": _ticket_view(p, [t])[0], "time_entries": [{**e, "employee_name": employees.get(e.get("employee_id") or "", "")} for e in entries],
            "external_updates": updates}


@router.patch("/tickets/{row_id}")
def update_ticket(row_id: str, body: TicketPatch, p: Principal = Depends(current_principal)):
    t = get_in_workspace(p, "bl_tickets", row_id, minimum=WS_EDITOR)
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    _enum(patch.get("status"), TICKET_STATUS, "status")
    _enum(patch.get("priority"), TICKET_PRIORITY, "priority")
    for key, table, label in (("customer_id", "bl_customers", "customer"), ("product_id", "bl_products", "product"), ("employee_id", "bl_employees", "employee")):
        if key in patch:
            if patch[key] == "":
                patch[key] = None
            else:
                _ref(p, table, patch[key], t["workspace_id"], label)
    if "opened_at" in patch:
        d = parse_dt(patch["opened_at"])
        if d is None:
            raise HTTPException(status_code=422, detail="invalid opened_at")
        patch["opened_at"] = iso(d)
    if "status" in patch:
        patch["closed_at"] = iso() if patch["status"] in ("resolved", "closed") else None
    row = _store().update("bl_tickets", row_id, organization_id=p.organization_id, patch=patch)
    audit(p, "billing.ticket.update", detail=f"{row_id} {','.join(patch)}")
    return _ticket_view(p, [row])[0]


@router.delete("/tickets/{row_id}")
def delete_ticket(row_id: str, p: Principal = Depends(current_principal)):
    get_in_workspace(p, "bl_tickets", row_id, minimum=WS_EDITOR)
    org = p.organization_id
    for table in ("bl_time_entries", "bl_external_updates"):
        for r in _store().list(table, organization_id=org, ticket_id=row_id):
            _store().delete(table, r["id"], organization_id=org)
    _store().delete("bl_tickets", row_id, organization_id=org)
    audit(p, "billing.ticket.delete", detail=row_id)
    return {"ok": True}


@router.post("/tickets/{row_id}/time")
def add_time(row_id: str, body: TimeEntryIn, p: Principal = Depends(current_principal)):
    t = get_in_workspace(p, "bl_tickets", row_id, minimum=WS_EDITOR)
    _ref(p, "bl_employees", body.employee_id, t["workspace_id"], "employee")
    row = _store().insert("bl_time_entries", {"id": new_id("tme"), "organization_id": p.organization_id, "workspace_id": t["workspace_id"], "ticket_id": row_id,
                                              "employee_id": body.employee_id or t.get("employee_id"), "description": body.description, "minutes": body.minutes,
                                              "entry_date": _date(body.entry_date, now().date()), "created_at": iso()})
    if t.get("status") == "open":
        _store().update("bl_tickets", row_id, organization_id=p.organization_id, patch={"status": "in_progress"})
    audit(p, "billing.time.create", detail=f"{row['id']} {row_id} {body.minutes}m")
    return row


@router.patch("/time/{row_id}")
def update_time(row_id: str, body: TimeEntryPatch, p: Principal = Depends(current_principal)):
    te = get_in_workspace(p, "bl_time_entries", row_id, minimum=WS_EDITOR)
    if te.get("billed_charge_id"):
        raise HTTPException(status_code=409, detail="הרישום כבר חויב. בטל את החיוב לפני שינוי.")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "entry_date" in patch:
        patch["entry_date"] = _date(patch["entry_date"], now().date())
    if patch.get("employee_id"):
        _ref(p, "bl_employees", patch["employee_id"], te["workspace_id"], "employee")
    row = _store().update("bl_time_entries", row_id, organization_id=p.organization_id, patch=patch)
    audit(p, "billing.time.update", detail=row_id)
    return row


@router.delete("/time/{row_id}")
def delete_time(row_id: str, p: Principal = Depends(current_principal)):
    te = get_in_workspace(p, "bl_time_entries", row_id, minimum=WS_EDITOR)
    if te.get("billed_charge_id"):
        raise HTTPException(status_code=409, detail="הרישום כבר חויב. בטל את החיוב לפני מחיקה.")
    _store().delete("bl_time_entries", row_id, organization_id=p.organization_id)
    audit(p, "billing.time.delete", detail=row_id)
    return {"ok": True}


@router.post("/tickets/{row_id}/external-link")
def external_link(row_id: str, days: int = Query(default=90, ge=1, le=365), p: Principal = Depends(current_principal)):
    """Signed link a customer can use to report what was done, without a login."""
    t = get_in_workspace(p, "bl_tickets", row_id, minimum=WS_EDITOR)
    try:
        token = engine.external_token(p.organization_id, t["id"], now().date().fromordinal(now().date().toordinal() + days))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    base = os.environ.get("CC_PUBLIC_URL", "").rstrip("/")
    audit(p, "billing.ticket.external_link", detail=row_id)
    return {"token": token, "url": f"{base}/u/{token}", "expires_in_days": days}


@router.get("/public/{token}")
def public_ticket(token: str):
    parsed = engine.parse_external_token(token)
    if not parsed:
        raise HTTPException(status_code=404, detail="הקישור אינו תקף או שפג תוקפו")
    org, ticket_id = parsed
    t = _store().get("bl_tickets", ticket_id, organization_id=org)
    if not t:
        raise HTTPException(status_code=404, detail="הקריאה לא נמצאה")
    customer = _store().get("bl_customers", t["customer_id"], organization_id=org) or {}
    settings = engine.settings_for(_store(), org, t["workspace_id"])
    updates = sorted(_store().list("bl_external_updates", organization_id=org, ticket_id=ticket_id), key=lambda e: str(e.get("created_at")), reverse=True)
    return {"ticket": {"number_label": engine.ticket_number(settings.get("ticket_prefix", "SC"), int(t.get("number") or 0)), "title": t["title"],
                       "status": t.get("status"), "opened_at": t.get("opened_at"), "customer_name": customer.get("name", "")},
            "business": settings.get("business") or {},
            "updates": [{"contact_name": u["contact_name"], "content": u["content"], "minutes": u.get("minutes"), "update_date": u.get("update_date")} for u in updates]}


@router.post("/public/{token}")
def public_update(token: str, body: ExternalUpdateIn):
    parsed = engine.parse_external_token(token)
    if not parsed:
        raise HTTPException(status_code=404, detail="הקישור אינו תקף או שפג תוקפו")
    org, ticket_id = parsed
    t = _store().get("bl_tickets", ticket_id, organization_id=org)
    if not t:
        raise HTTPException(status_code=404, detail="הקריאה לא נמצאה")
    row = _store().insert("bl_external_updates", {"id": new_id("xup"), "organization_id": org, "workspace_id": t["workspace_id"], "ticket_id": ticket_id,
                                                  "contact_name": body.contact_name.strip()[:120], "contact_phone": body.contact_phone.strip()[:40],
                                                  "content": body.content.strip(), "minutes": body.minutes, "update_date": _date(body.update_date, now().date()),
                                                  "created_at": iso(), "source": "external"})
    return {"ok": True, "id": row["id"]}


@router.get("/activities")
def list_activities(workspace_id: Optional[str] = None, limit: int = Query(default=200, ge=1, le=1000), p: Principal = Depends(current_principal)):
    out: list[Row] = []
    for ws in ([workspace_id] if workspace_id else visible_workspace_ids(p)):
        require_workspace(p, ws)
        out.extend(engine.activities(_store(), p.organization_id, ws, limit=limit))
    out.sort(key=lambda r: r["at"], reverse=True)
    return out[:limit]


# --- charges ------------------------------------------------------------------

def _charge_view(p: Principal, rows: list[Row]) -> list[Row]:
    if not rows:
        return rows
    customers = _names(p, "bl_customers", sorted({r["workspace_id"] for r in rows}))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["id"]] = len(_store().list("bl_charge_lines", organization_id=p.organization_id, charge_id=r["id"]))
    return [{**r, "customer_name": customers.get(r["customer_id"], ""), "lines": counts.get(r["id"], 0)} for r in rows]


@router.get("/charges")
def list_charges(workspace_id: Optional[str] = None, period: Optional[str] = None, status: Optional[str] = None, customer_id: Optional[str] = None,
                 p: Principal = Depends(current_principal)):
    rows = list_in_workspaces(p, "bl_charges", workspace_id)
    if period:
        rows = [r for r in rows if r.get("period") == period]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if customer_id:
        rows = [r for r in rows if r["customer_id"] == customer_id]
    rows.sort(key=lambda r: (r.get("period", ""), str(r.get("created_at"))), reverse=True)
    return _charge_view(p, rows)


@router.post("/charges/generate")
def generate_charges(body: GenerateIn, p: Principal = Depends(current_principal)):
    require_workspace(p, body.workspace_id, WS_EDITOR)
    if body.customer_id:
        _ref(p, "bl_customers", body.customer_id, body.workspace_id, "customer")
    out = engine.generate(_store(), p.organization_id, body.workspace_id, body.period, customer_id=body.customer_id, actor=p.actor)
    audit(p, "billing.charges.generate", detail=f"{body.workspace_id} {body.period} created={out['created']} updated={out['updated']}")
    return out


@router.post("/charges")
def create_manual_charge(body: ManualChargeIn, p: Principal = Depends(current_principal)):
    require_workspace(p, body.workspace_id, WS_EDITOR)
    _ref(p, "bl_customers", body.customer_id, body.workspace_id, "customer")
    org = p.organization_id
    existing = [c for c in _store().list("bl_charges", organization_id=org, workspace_id=body.workspace_id, period=body.period) if c["customer_id"] == body.customer_id]
    if existing:
        raise HTTPException(status_code=409, detail="כבר קיים חיוב ללקוח הזה בתקופה הזו")
    settings = engine.settings_for(_store(), org, body.workspace_id)
    charge = _store().insert("bl_charges", {"id": new_id("chg"), "organization_id": org, "workspace_id": body.workspace_id, "customer_id": body.customer_id,
                                            "period": body.period, "status": "draft", "created_at": iso(), "source": "manual", "notes": body.notes,
                                            "vat_pct": settings["vat_pct"]})
    for l in body.lines:
        _enum(l.kind, LINE_KIND, "kind")
        _store().insert("bl_charge_lines", {"id": new_id("chl"), "organization_id": org, "workspace_id": body.workspace_id, "charge_id": charge["id"], "created_at": iso(),
                                            "kind": l.kind, "ref_id": None, "description": l.description, "quantity": l.quantity, "unit_price": l.unit_price,
                                            "total": engine.money(l.quantity * l.unit_price)})
    charge = engine.recompute(_store(), org, {**charge, "vat_pct_override": settings["vat_pct"]})
    audit(p, "billing.charge.create", detail=charge["id"])
    return _charge_view(p, [charge])[0]


@router.get("/charges/{row_id}")
def get_charge(row_id: str, p: Principal = Depends(current_principal)):
    c = get_in_workspace(p, "bl_charges", row_id)
    lines = sorted(_store().list("bl_charge_lines", organization_id=p.organization_id, charge_id=row_id), key=lambda l: str(l.get("created_at")))
    customer = _store().get("bl_customers", c["customer_id"], organization_id=p.organization_id) or {}
    return {"charge": _charge_view(p, [c])[0], "lines": lines, "customer": customer}


@router.patch("/charges/{row_id}")
def update_charge(row_id: str, body: ChargePatch, p: Principal = Depends(current_principal)):
    c = get_in_workspace(p, "bl_charges", row_id, minimum=WS_EDITOR)
    org = p.organization_id
    patch: Row = {}
    if body.notes is not None:
        patch["notes"] = body.notes
    if body.vat_pct is not None:
        patch["vat_pct_override"] = body.vat_pct
        patch["vat_pct"] = body.vat_pct
    if body.status is not None:
        _enum(body.status, CHARGE_STATUS, "status")
        old = c.get("status", "draft")
        if body.status == "issued" and old in ("draft", "paid"):
            patch["issued_at"] = c.get("issued_at") or iso()
            patch["paid_at"] = None
            if old == "draft":
                start, end = engine.period_bounds(c["period"])
                for t in _store().list("bl_tickets", organization_id=org, customer_id=c["customer_id"]):
                    for te in _store().list("bl_time_entries", organization_id=org, ticket_id=t["id"]):
                        d = engine.to_date(te.get("entry_date"))
                        if d and start <= d <= end and not te.get("billed_charge_id") and c.get("customer_id"):
                            if any(l.get("kind") == "hours" for l in _store().list("bl_charge_lines", organization_id=org, charge_id=row_id)):
                                _store().update("bl_time_entries", te["id"], organization_id=org, patch={"billed_charge_id": row_id})
        elif body.status == "paid":
            patch["issued_at"] = c.get("issued_at") or iso()
            patch["paid_at"] = iso(parse_dt(body.paid_at) or now()) if body.paid_at else iso()
        elif body.status == "cancelled":
            for te in _store().list("bl_time_entries", organization_id=org, billed_charge_id=row_id):
                _store().update("bl_time_entries", te["id"], organization_id=org, patch={"billed_charge_id": None})
        elif body.status == "draft":
            if old != "draft":
                for te in _store().list("bl_time_entries", organization_id=org, billed_charge_id=row_id):
                    _store().update("bl_time_entries", te["id"], organization_id=org, patch={"billed_charge_id": None})
            patch["issued_at"] = None
            patch["paid_at"] = None
        patch["status"] = body.status
    row = _store().update("bl_charges", row_id, organization_id=org, patch=patch)
    if body.vat_pct is not None:
        row = engine.recompute(_store(), org, row)
    audit(p, "billing.charge.update", detail=f"{row_id} {','.join(patch)}")
    return _charge_view(p, [row])[0]


@router.delete("/charges/{row_id}")
def delete_charge(row_id: str, p: Principal = Depends(current_principal)):
    c = get_in_workspace(p, "bl_charges", row_id, minimum=WS_EDITOR)
    if c.get("status") not in ("draft", "cancelled"):
        raise HTTPException(status_code=409, detail="אפשר למחוק רק טיוטה או חיוב מבוטל")
    org = p.organization_id
    for l in _store().list("bl_charge_lines", organization_id=org, charge_id=row_id):
        _store().delete("bl_charge_lines", l["id"], organization_id=org)
    _store().delete("bl_charges", row_id, organization_id=org)
    audit(p, "billing.charge.delete", detail=row_id)
    return {"ok": True}


@router.post("/charges/{row_id}/lines")
def add_line(row_id: str, body: ChargeLineIn, p: Principal = Depends(current_principal)):
    c = get_in_workspace(p, "bl_charges", row_id, minimum=WS_EDITOR)
    if c.get("status") != "draft":
        raise HTTPException(status_code=409, detail="אפשר להוסיף שורות רק לטיוטה")
    _enum(body.kind, LINE_KIND, "kind")
    org = p.organization_id
    line = _store().insert("bl_charge_lines", {"id": new_id("chl"), "organization_id": org, "workspace_id": c["workspace_id"], "charge_id": row_id, "created_at": iso(),
                                               "kind": body.kind, "ref_id": None, "description": body.description, "quantity": body.quantity,
                                               "unit_price": body.unit_price, "total": engine.money(body.quantity * body.unit_price)})
    engine.recompute(_store(), org, c)
    audit(p, "billing.charge.line", detail=f"{row_id} +{line['id']}")
    return line


@router.delete("/charges/{row_id}/lines/{line_id}")
def delete_line(row_id: str, line_id: str, p: Principal = Depends(current_principal)):
    c = get_in_workspace(p, "bl_charges", row_id, minimum=WS_EDITOR)
    if c.get("status") != "draft":
        raise HTTPException(status_code=409, detail="אפשר למחוק שורות רק מטיוטה")
    org = p.organization_id
    line = _store().get("bl_charge_lines", line_id, organization_id=org)
    if not line or line["charge_id"] != row_id:
        raise HTTPException(status_code=404, detail="line not found")
    _store().delete("bl_charge_lines", line_id, organization_id=org)
    engine.recompute(_store(), org, c)
    audit(p, "billing.charge.line", detail=f"{row_id} -{line_id}")
    return {"ok": True}


def _period_label(period: str) -> str:
    months = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
    try:
        return f"{months[int(period[5:7]) - 1]} {period[:4]}"
    except (ValueError, IndexError):
        return period


@router.get("/charges/{row_id}/print", response_class=HTMLResponse)
def print_charge(row_id: str, p: Principal = Depends(current_principal)):
    c = get_in_workspace(p, "bl_charges", row_id)
    org = p.organization_id
    lines = sorted(_store().list("bl_charge_lines", organization_id=org, charge_id=row_id), key=lambda l: str(l.get("created_at")))
    customer = _store().get("bl_customers", c["customer_id"], organization_id=org) or {}
    settings = engine.settings_for(_store(), org, c["workspace_id"])
    return HTMLResponse(exports.charge_html(c, lines, customer, settings.get("business") or {}, _period_label(c["period"])))


@router.get("/exports/charges.xlsx")
def export_charges(workspace_id: str, period: Optional[str] = None, p: Principal = Depends(current_principal)):
    require_workspace(p, workspace_id)
    rows = list_charges(workspace_id=workspace_id, period=period, status=None, customer_id=None, p=p)
    status_he = {"draft": "טיוטה", "issued": "הופק", "paid": "שולם", "cancelled": "בוטל"}
    lines_rows = []
    for c in rows:
        for l in _store().list("bl_charge_lines", organization_id=p.organization_id, charge_id=c["id"]):
            lines_rows.append([c["period"], c["customer_name"], l.get("kind"), l.get("description"), float(l.get("quantity") or 0), float(l.get("unit_price") or 0), float(l.get("total") or 0)])
    data = exports.xlsx([
        ("חיובים", ["תקופה", "לקוח", "סטטוס", "לפני מע\"מ", "מע\"מ", "סה\"כ", "הופק", "שולם"],
         [[c["period"], c["customer_name"], status_he.get(c.get("status"), c.get("status")), float(c.get("subtotal") or 0), float(c.get("vat") or 0), float(c.get("total") or 0),
           str(c.get("issued_at") or "")[:10], str(c.get("paid_at") or "")[:10]] for c in rows]),
        ("שורות", ["תקופה", "לקוח", "סוג", "תיאור", "כמות", "מחיר יחידה", "סה\"כ"], lines_rows),
    ])
    name = f"charges_{period or 'all'}.xlsx"
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={name}"})


# --- reports ------------------------------------------------------------------

@router.get("/reports/hours")
def report_hours(workspace_id: str, customer_id: Optional[str] = None, from_: Optional[str] = Query(default=None, alias="from"), to: Optional[str] = None,
                 format: str = "json", p: Principal = Depends(current_principal)):
    require_workspace(p, workspace_id)
    start = engine.to_date(from_) if from_ else None
    end = engine.to_date(to) if to else None
    rep = engine.hours_report(_store(), p.organization_id, workspace_id, customer_id=customer_id, start=start, end=end)
    customer = _store().get("bl_customers", customer_id, organization_id=p.organization_id) if customer_id else None
    cname = customer["name"] if customer else "כל הלקוחות"
    if format == "xlsx":
        data = exports.xlsx([("דוח שעות", ["תאריך", "קריאה", "כותרת", "לקוח", "מטפל", "תיאור", "דקות"],
                              [[r["entry_date"], r["ticket_number"], r["ticket_title"], r["customer_name"], r["employee_name"], r["description"], r["minutes"]] for r in rep["entries"]]),
                             ("לפי מטפל", ["מטפל", "דקות"], [[x["employee_name"], x["minutes"]] for x in rep["by_employee"]])])
        return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename=hours_{from_ or ''}_{to or ''}.xlsx"})
    if format == "html":
        settings = engine.settings_for(_store(), p.organization_id, workspace_id)
        return HTMLResponse(exports.hours_html(rep, cname, from_ or "", to or "", settings.get("business") or {}))
    return {**rep, "customer_name": cname}


@router.get("/overview")
def billing_overview(workspace_id: Optional[str] = None, months: int = Query(default=6, ge=1, le=24), p: Principal = Depends(current_principal)):
    ws_ids = [workspace_id] if workspace_id else visible_workspace_ids(p)
    for ws in ws_ids:
        require_workspace(p, ws)
    out = engine.overview(_store(), p.organization_id, ws_ids, months=months)
    recent = []
    for ws in ws_ids:
        recent.extend(engine.activities(_store(), p.organization_id, ws, limit=10))
    recent.sort(key=lambda r: r["at"], reverse=True)
    out["recent"] = recent[:10]
    out["drafts"] = sum(1 for ws in ws_ids for c in _store().list("bl_charges", organization_id=p.organization_id, workspace_id=ws) if c.get("status") == "draft")
    return out


# --- expenses -----------------------------------------------------------------

def _prep_expense(p: Principal, row: Row, current: Optional[Row]) -> None:
    _enum(row.get("currency"), CURRENCIES, "currency")
    _enum(row.get("category"), EXPENSE_CATEGORY, "category")
    row["expense_date"] = _date(row.get("expense_date"), now().date())
    settings = engine.settings_for(_store(), p.organization_id, row["workspace_id"])
    manual = row.pop("rate", None)
    if manual:
        rate, source = float(manual), "manual"
    else:
        rate, source = engine.fx_rate(_store(), p.organization_id, row.get("currency", "ILS"), engine.to_date(row["expense_date"]), settings)
    row["rate_used"] = rate
    row["rate_source"] = source
    row["amount_ils"] = engine.money(float(row.get("amount") or 0) * rate)


_crud("expenses", "bl_expenses", "exp", ExpenseIn, ExpensePatch, prepare=_prep_expense)


@router.get("/exports/expenses.xlsx")
def export_expenses(workspace_id: str, p: Principal = Depends(current_principal)):
    require_workspace(p, workspace_id)
    rows = sorted(_store().list("bl_expenses", organization_id=p.organization_id, workspace_id=workspace_id), key=lambda r: str(r.get("expense_date")), reverse=True)
    cat = {"software": "תוכנה", "database": "דאטהבייס", "staff": "עובדים", "equipment": "ציוד", "office": "משרד", "infra": "תשתית", "other": "אחר"}
    data = exports.xlsx([("הוצאות", ["תאריך", "שם", "קטגוריה", "סכום", "מטבע", "שער", "סכום בש\"ח", "חוזרת", "תיאור"],
                          [[str(r.get("expense_date"))[:10], r["name"], cat.get(r.get("category"), r.get("category")), float(r.get("amount") or 0), r.get("currency"),
                            float(r.get("rate_used") or 1), float(r.get("amount_ils") or 0), "כן" if r.get("recurring") else "לא", r.get("description", "")] for r in rows])])
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=expenses.xlsx"})


@router.get("/fx")
def list_fx(currency: Optional[str] = None, p: Principal = Depends(current_principal)):
    rows = _store().list("bl_fx_rates", organization_id=p.organization_id)
    if currency:
        rows = [r for r in rows if r["currency"] == currency.upper()]
    return sorted(rows, key=lambda r: str(r.get("rate_date")), reverse=True)[:200]


@router.post("/fx")
def set_fx(body: FxRateIn, p: Principal = Depends(current_principal)):
    _enum(body.currency.upper(), ("USD", "EUR"), "currency")
    d = _date(body.rate_date)
    org = p.organization_id
    for r in _store().list("bl_fx_rates", organization_id=org, currency=body.currency.upper()):
        if str(r.get("rate_date"))[:10] == d:
            return _store().update("bl_fx_rates", r["id"], organization_id=org, patch={"rate": body.rate})
    return _store().insert("bl_fx_rates", {"id": new_id("fx"), "organization_id": org, "currency": body.currency.upper(), "rate_date": d, "rate": body.rate, "created_at": iso()})


# --- knowledge ----------------------------------------------------------------

def _prep_knowledge(p: Principal, row: Row, current: Optional[Row]) -> None:
    if row.get("product_id") == "":
        row["product_id"] = None
    elif row.get("product_id"):
        _ref(p, "bl_products", row["product_id"], row["workspace_id"], "product")
    row["tags"] = [t.strip() for t in (row.get("tags") or []) if t and t.strip()]


def _knowledge_view(p: Principal, rows: list[Row]) -> list[Row]:
    if not rows:
        return rows
    products = _names(p, "bl_products", sorted({r["workspace_id"] for r in rows}))
    return [{**r, "product_name": products.get(r.get("product_id") or "", "")} for r in rows]


_crud("knowledge", "bl_knowledge", "kb", KnowledgeIn, KnowledgePatch, prepare=_prep_knowledge, enrich=_knowledge_view)


# --- settings -----------------------------------------------------------------

@router.get("/settings")
def get_settings(workspace_id: str, p: Principal = Depends(current_principal)):
    require_workspace(p, workspace_id)
    return engine.settings_for(_store(), p.organization_id, workspace_id)


@router.put("/settings")
def put_settings(workspace_id: str, body: SettingsIn, p: Principal = Depends(current_principal)):
    require_workspace(p, workspace_id, WS_ADMIN)
    _enum(body.currency, CURRENCIES, "currency")
    org = p.organization_id
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    rows = _store().list("bl_settings", organization_id=org, workspace_id=workspace_id)
    if rows:
        row = _store().update("bl_settings", rows[0]["id"], organization_id=org, patch=patch)
    else:
        row = _store().insert("bl_settings", {"id": f"set_{workspace_id}", "organization_id": org, "workspace_id": workspace_id, "created_at": iso(), **patch})
    audit(p, "billing.settings.update", detail=f"{workspace_id} {','.join(patch)}")
    return engine.settings_for(_store(), org, workspace_id)


# --- import from the old system ----------------------------------------------

_STATUS_MAP = {"in-progress": "in_progress", "פתוח": "open", "בטיפול": "in_progress", "נפתר": "resolved", "סגור": "closed"}
_PRIORITY_MAP = {"רגילה": "medium", "נמוכה": "low", "גבוהה": "high", "קריטית": "critical"}
_CATEGORY_MAP = {"תוכנה": "software", "דאטהבייס": "database", "עובדים": "staff", "ציוד": "equipment", "משרד": "office", "אחר": "other"}


@router.post("/import")
def import_legacy(body: ImportIn, p: Principal = Depends(current_principal)):
    """Idempotent import of the old database (rows keyed by their legacy id)."""
    ws = body.workspace_id
    require_workspace(p, ws, WS_ADMIN)
    store, org = _store(), p.organization_id
    report: dict[str, dict[str, int]] = {}
    idmap: dict[str, dict[str, str]] = {}

    def existing(table: str) -> dict[str, str]:
        return {r["legacy_id"]: r["id"] for r in store.list(table, organization_id=org, workspace_id=ws) if r.get("legacy_id")}

    def put(table: str, kind: str, legacy: str, row: Row, prefix: str) -> Optional[str]:
        rep = report.setdefault(kind, {"inserted": 0, "skipped": 0, "errors": 0})
        known = idmap.setdefault(kind, existing(table))
        if legacy in known:
            rep["skipped"] += 1
            return known[legacy]
        try:
            new = store.insert(table, {"id": new_id(prefix), "organization_id": org, "workspace_id": ws, "created_at": iso(), "legacy_id": legacy, **row})
        except Exception:
            rep["errors"] += 1
            return None
        known[legacy] = new["id"]
        rep["inserted"] += 1
        return new["id"]

    def ref(kind: str, legacy: Optional[str]) -> Optional[str]:
        return idmap.get(kind, {}).get(legacy or "") if legacy else None

    for r in body.employees:
        put("bl_employees", "employees", r["id"], {"name": r.get("name") or "", "email": r.get("email") or "", "phone": r.get("phone") or "", "position": r.get("position") or "",
                                                   "role": r.get("role") if r.get("role") in EMPLOYEE_ROLE else "support", "hourly_rate": r.get("hourly_rate"), "active": True}, "emp")
    idmap.setdefault("employees", existing("bl_employees"))
    for r in body.customers:
        row = {"name": r.get("name") or "", "email": r.get("email") or "", "phone": r.get("phone") or "", "contact_person": r.get("contact_person") or "",
               "address": r.get("address") or "", "status": "active", "bill_hours": False}
        created: list[str] = []
        row["client_id"] = usage_engine.resolve_client(store, org, ws, client_id=None, name=row["name"], created=created, source="billing-import")
        put("bl_customers", "customers", r["id"], row, "cus")
    idmap.setdefault("customers", existing("bl_customers"))
    for r in body.products:
        put("bl_products", "products", r["id"], {"name": r.get("name") or "", "description": r.get("description") or "", "price": r.get("price") or 0,
                                                 "has_light_user": bool(r.get("has_light_user")), "light_user_price": r.get("light_user_price") or 0}, "prd")
    idmap.setdefault("products", existing("bl_products"))
    for r in body.services:
        put("bl_services", "services", r["id"], {"description": r.get("description") or "", "price": r.get("price") or 0, "recurring": bool(r.get("recurring"))}, "svc")
    for r in body.product_users:
        cid, pid = ref("customers", r.get("customer_id")), ref("products", r.get("product_id"))
        if not cid or not pid:
            report.setdefault("product_users", {"inserted": 0, "skipped": 0, "errors": 0})["errors"] += 1
            continue
        put("bl_subscriptions", "product_users", r["id"], {"customer_id": cid, "kind": "product", "product_id": pid, "user_count": r.get("user_count") or 0,
                                                           "light_user_count": r.get("light_user_count") or 0, "quantity": 1,
                                                           "valid_from": _date(r.get("valid_from"), now().date()), "valid_until": _date(r.get("valid_until"))}, "sub")
    number = _next_number(p, ws)
    for r in sorted(body.service_tickets, key=lambda x: str(x.get("created_at") or "")):
        cid = ref("customers", r.get("customer_id"))
        if not cid:
            report.setdefault("service_tickets", {"inserted": 0, "skipped": 0, "errors": 0})["errors"] += 1
            continue
        opened = parse_dt(r.get("created_at")) or now()
        status = _STATUS_MAP.get(r.get("status") or "", r.get("status") or "open")
        legacy_title = r.get("title") or ""
        before = report.get("service_tickets", {}).get("inserted", 0)
        put("bl_tickets", "service_tickets", r["id"], {
            "number": number, "customer_id": cid, "product_id": ref("products", r.get("product_id")), "employee_id": ref("employees", r.get("assigned_employee_id")),
            "title": legacy_title, "description": r.get("description") or "", "status": status if status in TICKET_STATUS else "open",
            "priority": _PRIORITY_MAP.get(r.get("priority") or "", r.get("priority") or "medium") if (r.get("priority") or "medium") not in TICKET_PRIORITY else r.get("priority") or "medium",
            "contact_person": r.get("contact_person") or "", "contact_phone": r.get("contact_phone") or "", "group_name": r.get("group_name") or "",
            "image_url": r.get("image_url") or "", "opened_at": iso(opened), "closed_at": iso(parse_dt(r.get("updated_at")) or opened) if status in ("resolved", "closed") else None,
            "legacy_title": legacy_title}, "tkt")
        if report.get("service_tickets", {}).get("inserted", 0) > before:
            number += 1
    for r in body.service_time_entries:
        tid = ref("service_tickets", r.get("ticket_id"))
        if not tid:
            report.setdefault("service_time_entries", {"inserted": 0, "skipped": 0, "errors": 0})["errors"] += 1
            continue
        put("bl_time_entries", "service_time_entries", r["id"], {"ticket_id": tid, "employee_id": ref("employees", r.get("employee_id")), "description": r.get("description") or "",
                                                                 "minutes": int(r.get("time_spent") or 0), "entry_date": _date(r.get("entry_date"), now().date())}, "tme")
    for r in body.external_ticket_updates:
        tid = ref("service_tickets", r.get("ticket_id"))
        if not tid:
            report.setdefault("external_ticket_updates", {"inserted": 0, "skipped": 0, "errors": 0})["errors"] += 1
            continue
        put("bl_external_updates", "external_ticket_updates", r["id"], {"ticket_id": tid, "contact_name": r.get("contact_name") or "", "contact_phone": r.get("contact_phone") or "",
                                                                        "content": r.get("update_content") or "", "minutes": r.get("treatment_time"),
                                                                        "update_date": _date(r.get("update_date"), now().date())}, "xup")
    for r in body.monthly_summaries:
        cid = ref("customers", r.get("customer_id"))
        if not cid:
            report.setdefault("monthly_summaries", {"inserted": 0, "skipped": 0, "errors": 0})["errors"] += 1
            continue
        period = f"{int(r.get('year') or 0):04d}-{int(r.get('month') or 1):02d}"
        total = engine.money(r.get("total_amount"))
        put("bl_charges", "monthly_summaries", r["id"], {"customer_id": cid, "period": period, "status": "paid" if r.get("paid") else "issued",
                                                         "subtotal": total, "vat_pct": 0, "vat": 0, "total": total, "issued_at": iso(parse_dt(r.get("created_at")) or now()),
                                                         "paid_at": iso(parse_dt(r.get("payment_date"))) if r.get("paid") and parse_dt(r.get("payment_date")) else None,
                                                         "source": "import"}, "chg")
    idmap.setdefault("monthly_summaries", existing("bl_charges"))
    charges_by_key = {(c["customer_id"], c["period"]): c for c in store.list("bl_charges", organization_id=org, workspace_id=ws)}
    products_by_id = {x["id"]: x for x in store.list("bl_products", organization_id=org, workspace_id=ws)}
    for r in body.billing_items:
        cid, pid = ref("customers", r.get("customer_id")), ref("products", r.get("product_id"))
        d = engine.to_date(r.get("billing_date"))
        if not cid or not d:
            report.setdefault("billing_items", {"inserted": 0, "skipped": 0, "errors": 0})["errors"] += 1
            continue
        period = d.strftime("%Y-%m")
        charge = charges_by_key.get((cid, period))
        if not charge:
            charge = store.insert("bl_charges", {"id": new_id("chg"), "organization_id": org, "workspace_id": ws, "customer_id": cid, "period": period, "status": "draft",
                                                 "created_at": iso(), "source": "import", "vat_pct": 0})
            charges_by_key[(cid, period)] = charge
        qty, unit = float(r.get("quantity") or 1), engine.money(r.get("price_per_unit"))
        put("bl_charge_lines", "billing_items", r["id"], {"charge_id": charge["id"], "kind": "product", "ref_id": pid, "description": products_by_id.get(pid or "", {}).get("name", "פריט חיוב"),
                                                          "quantity": qty, "unit_price": unit, "total": engine.money(qty * unit)}, "chl")
    for r in body.expenses:
        put("bl_expenses", "expenses", r["id"], {"name": r.get("name") or "", "amount": r.get("amount") or 0, "currency": (r.get("currency") or "ILS").upper(),
                                                 "rate_used": (float(r.get("amount_in_ils") or 0) / float(r.get("amount"))) if float(r.get("amount") or 0) else 1,
                                                 "amount_ils": r.get("amount_in_ils") or r.get("amount") or 0, "category": _CATEGORY_MAP.get(r.get("category") or "", r.get("category") or "other"),
                                                 "expense_date": _date(r.get("date"), now().date()), "description": r.get("description") or "", "recurring": bool(r.get("recurring")),
                                                 "rate_source": "import"}, "exp")
    for r in body.knowledge_items:
        put("bl_knowledge", "knowledge_items", r["id"], {"product_id": ref("products", r.get("product_id")), "title": r.get("title") or "", "content": r.get("content") or "",
                                                         "category": r.get("category") or "", "tags": r.get("tags") or []}, "kb")
    audit(p, "billing.import", detail=f"{ws} " + " ".join(f"{k}={v['inserted']}/{v['skipped']}/{v['errors']}" for k, v in report.items()))
    return {"workspace_id": ws, "report": report}


@router.post("/import/supabase")
def import_from_supabase(body: LegacySupabaseIn, p: Principal = Depends(current_principal)):
    """One-shot migration from the old Lovable/Supabase billing app: log in to
    the old project as the given user, read all tables, import them. Safe to
    re-run (rows are keyed by legacy id). Credentials are not stored."""
    require_workspace(p, body.workspace_id, WS_ADMIN)
    try:
        data = legacy.fetch_all(body.supabase_url, body.anon_key, body.email, body.password)
    except legacy.LegacyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:   # network / parsing
        raise HTTPException(status_code=502, detail=f"שגיאה מול Supabase הישן: {type(exc).__name__}")
    counts = {k: len(v) for k, v in data.items()}
    if body.dry_run:
        audit(p, "billing.import.supabase", detail=f"{body.workspace_id} dry-run " + " ".join(f"{k}={v}" for k, v in counts.items()))
        return {"workspace_id": body.workspace_id, "fetched": counts, "report": None}
    out = import_legacy(ImportIn(workspace_id=body.workspace_id, **data), p)
    audit(p, "billing.import.supabase", detail=f"{body.workspace_id} " + " ".join(f"{k}={v}" for k, v in counts.items()))
    return {**out, "fetched": counts}
