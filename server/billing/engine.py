"""Billing engine: monthly charge generation, hours report, activity feed,
FX conversion and dashboard numbers. Pure functions over store rows so they
are easy to test; the routes only do permissions and I/O.
"""

from __future__ import annotations

import base64
import calendar
import hashlib
import hmac
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional

from cc.service import iso, new_id, now, parse_dt

Row = dict[str, Any]

DEFAULT_FX = {"USD": 3.7, "EUR": 4.0, "ILS": 1.0}
DEFAULT_SETTINGS = {"vat_pct": 18.0, "hourly_rate": 0.0, "currency": "ILS", "ticket_prefix": "SC", "business": {}, "fx_defaults": DEFAULT_FX}


def money(v: Any) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def to_date(v: Any) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        d = parse_dt(v)
        return d.date() if d else None


def period_bounds(period: str) -> tuple[date, date]:
    y, m = int(period[:4]), int(period[5:7])
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def settings_for(store, org: str, ws: str) -> Row:
    rows = store.list("bl_settings", organization_id=org, workspace_id=ws)
    merged = dict(DEFAULT_SETTINGS)
    if rows:
        merged.update({k: v for k, v in rows[0].items() if k not in ("id", "organization_id", "workspace_id", "created_at")})
    merged["fx_defaults"] = {**DEFAULT_FX, **(merged.get("fx_defaults") or {})}
    return merged


def fx_rate(store, org: str, currency: str, on: Optional[date], settings: Row) -> tuple[float, str]:
    """Rate to ILS for a currency on a date: the latest stored rate on or before
    the date, else the workspace default. Returns (rate, source)."""
    cur = (currency or "ILS").upper()
    if cur == "ILS":
        return 1.0, "fixed"
    on = on or now().date()
    best: Optional[Row] = None
    for r in store.list("bl_fx_rates", organization_id=org, currency=cur):
        d = to_date(r.get("rate_date"))
        if d and d <= on and (best is None or d > to_date(best["rate_date"])):
            best = r
    if best:
        return float(best["rate"]), f"rate {best['rate_date']}"
    return float((settings.get("fx_defaults") or {}).get(cur) or DEFAULT_FX.get(cur, 1.0)), "default"


def active_fraction(valid_from: Any, valid_until: Any, start: date, end: date) -> float:
    """Share of the month a subscription was active (1.0 = whole month)."""
    vf, vu = to_date(valid_from), to_date(valid_until)
    s = max(start, vf) if vf else start
    e = min(end, vu) if vu else end
    if e < s:
        return 0.0
    return round(((e - s).days + 1) / ((end - start).days + 1), 4)


def ticket_number(prefix: str, n: int) -> str:
    return f"{prefix}-{n:06d}"


# --- charge generation -------------------------------------------------------

def build_lines(customer: Row, subs: list[Row], products: dict[str, Row], services: dict[str, Row],
                time_entries: list[Row], employees: dict[str, Row], settings: Row, start: date, end: date) -> list[Row]:
    """Automatic lines for one customer and one month."""
    lines: list[Row] = []
    for s in subs:
        frac = active_fraction(s.get("valid_from"), s.get("valid_until"), start, end)
        if frac <= 0:
            continue
        suffix = "" if frac >= 0.999 else f" (חלקי {int(round(frac * 100))}%)"
        if s.get("kind", "product") == "product":
            p = products.get(s.get("product_id") or "")
            if not p:
                continue
            users = int(s.get("user_count") or 0)
            if users:
                unit = money(p.get("price"))
                lines.append({"kind": "product", "ref_id": p["id"], "description": f"{p['name']} · {users} משתמשים{suffix}",
                              "quantity": users, "unit_price": unit, "total": money(users * unit * frac)})
            light = int(s.get("light_user_count") or 0)
            if light and p.get("has_light_user"):
                unit = money(p.get("light_user_price"))
                lines.append({"kind": "light", "ref_id": p["id"], "description": f"{p['name']} · {light} משתמשי Light{suffix}",
                              "quantity": light, "unit_price": unit, "total": money(light * unit * frac)})
        else:
            sv = services.get(s.get("service_id") or "")
            if not sv:
                continue
            qty = float(s.get("quantity") or 1)
            unit = money(sv.get("price"))
            if sv.get("recurring"):
                lines.append({"kind": "service", "ref_id": sv["id"], "description": f"{sv['description']}{suffix}",
                              "quantity": qty, "unit_price": unit, "total": money(qty * unit * frac)})
            else:
                # one-off: charged in the month it starts
                vf = to_date(s.get("valid_from"))
                if vf and start <= vf <= end:
                    lines.append({"kind": "service", "ref_id": sv["id"], "description": sv["description"],
                                  "quantity": qty, "unit_price": unit, "total": money(qty * unit)})
    if customer.get("bill_hours"):
        total_min = 0
        rate_sum = 0.0
        for te in time_entries:
            d = to_date(te.get("entry_date"))
            if not d or not (start <= d <= end) or te.get("billed_charge_id"):
                continue
            minutes = int(te.get("minutes") or 0)
            emp = employees.get(te.get("employee_id") or "")
            rate = customer.get("hourly_rate") or (emp or {}).get("hourly_rate") or settings.get("hourly_rate") or 0
            total_min += minutes
            rate_sum += minutes / 60 * float(rate)
        if total_min:
            hours = round(total_min / 60, 2)
            lines.append({"kind": "hours", "ref_id": None, "description": f"שעות טיפול · {hours} שעות",
                          "quantity": hours, "unit_price": money(rate_sum / hours) if hours else 0, "total": money(rate_sum)})
    return lines


def totals(lines: list[Row], vat_pct: float) -> dict[str, float]:
    subtotal = money(sum(money(l.get("total")) for l in lines))
    vat = money(subtotal * float(vat_pct or 0) / 100)
    return {"subtotal": subtotal, "vat_pct": float(vat_pct or 0), "vat": vat, "total": money(subtotal + vat)}


def generate(store, org: str, ws: str, period: str, *, customer_id: Optional[str], actor: str) -> dict[str, Any]:
    """Create or refresh draft charges for a month. Issued / paid charges are
    left alone; manual lines on a draft survive the refresh."""
    start, end = period_bounds(period)
    settings = settings_for(store, org, ws)
    customers = [c for c in store.list("bl_customers", organization_id=org, workspace_id=ws)
                 if c.get("status", "active") != "closed" and (not customer_id or c["id"] == customer_id)]
    products = {p["id"]: p for p in store.list("bl_products", organization_id=org, workspace_id=ws)}
    services = {s["id"]: s for s in store.list("bl_services", organization_id=org, workspace_id=ws)}
    employees = {e["id"]: e for e in store.list("bl_employees", organization_id=org, workspace_id=ws)}
    subs_all = store.list("bl_subscriptions", organization_id=org, workspace_id=ws)
    tickets = {t["id"]: t for t in store.list("bl_tickets", organization_id=org, workspace_id=ws)}
    entries_all = store.list("bl_time_entries", organization_id=org, workspace_id=ws)
    existing = {c["customer_id"]: c for c in store.list("bl_charges", organization_id=org, workspace_id=ws, period=period)}

    created = updated = skipped = 0
    out_ids: list[str] = []
    for c in customers:
        subs = [s for s in subs_all if s["customer_id"] == c["id"]]
        entries = [e for e in entries_all if tickets.get(e["ticket_id"], {}).get("customer_id") == c["id"]]
        lines = build_lines(c, subs, products, services, entries, employees, settings, start, end)
        charge = existing.get(c["id"])
        if charge and charge.get("status") != "draft":
            skipped += 1
            continue
        if not lines and not charge:
            continue   # nothing to bill, nothing to refresh
        manual: list[Row] = []
        if charge:
            for l in store.list("bl_charge_lines", organization_id=org, charge_id=charge["id"]):
                if l.get("kind") == "manual":
                    manual.append(l)
                else:
                    store.delete("bl_charge_lines", l["id"], organization_id=org)
            updated += 1
        else:
            charge = store.insert("bl_charges", {"id": new_id("chg"), "organization_id": org, "workspace_id": ws, "customer_id": c["id"],
                                                 "period": period, "status": "draft", "created_at": iso(), "source": "auto"})
            created += 1
        for l in lines:
            store.insert("bl_charge_lines", {"id": new_id("chl"), "organization_id": org, "workspace_id": ws, "charge_id": charge["id"],
                                             "created_at": iso(), **l})
        vat_pct = charge.get("vat_pct_override", settings["vat_pct"])
        t = totals(lines + manual, vat_pct)
        store.update("bl_charges", charge["id"], organization_id=org, patch={**t, "generated_at": iso(), "generated_by": actor})
        out_ids.append(charge["id"])
    return {"period": period, "created": created, "updated": updated, "skipped_non_draft": skipped, "charge_ids": out_ids}


def recompute(store, org: str, charge: Row) -> Row:
    lines = store.list("bl_charge_lines", organization_id=org, charge_id=charge["id"])
    t = totals(lines, charge.get("vat_pct_override", charge.get("vat_pct") or 0))
    return store.update("bl_charges", charge["id"], organization_id=org, patch=t)


# --- hours report -------------------------------------------------------------

def hours_report(store, org: str, ws: str, *, customer_id: Optional[str], start: Optional[date], end: Optional[date]) -> dict[str, Any]:
    tickets = {t["id"]: t for t in store.list("bl_tickets", organization_id=org, workspace_id=ws)}
    employees = {e["id"]: e["name"] for e in store.list("bl_employees", organization_id=org, workspace_id=ws)}
    customers = {c["id"]: c["name"] for c in store.list("bl_customers", organization_id=org, workspace_id=ws)}
    rows = []
    for te in store.list("bl_time_entries", organization_id=org, workspace_id=ws):
        t = tickets.get(te["ticket_id"])
        if not t or (customer_id and t["customer_id"] != customer_id):
            continue
        d = to_date(te.get("entry_date"))
        if (start and d and d < start) or (end and d and d > end):
            continue
        rows.append({"id": te["id"], "entry_date": str(te.get("entry_date"))[:10], "ticket_id": t["id"], "ticket_number": t.get("number"),
                     "ticket_title": t["title"], "customer_id": t["customer_id"], "customer_name": customers.get(t["customer_id"], ""),
                     "employee_name": employees.get(te.get("employee_id") or "", ""), "minutes": int(te.get("minutes") or 0),
                     "description": te.get("description") or t.get("description") or "", "billed": bool(te.get("billed_charge_id"))})
    rows.sort(key=lambda r: (r["entry_date"], r["ticket_number"] or 0), reverse=True)
    total = sum(r["minutes"] for r in rows)
    by_employee: dict[str, int] = {}
    by_ticket: dict[str, dict] = {}
    for r in rows:
        by_employee[r["employee_name"] or "—"] = by_employee.get(r["employee_name"] or "—", 0) + r["minutes"]
        bt = by_ticket.setdefault(r["ticket_id"], {"ticket_id": r["ticket_id"], "ticket_number": r["ticket_number"], "ticket_title": r["ticket_title"], "minutes": 0})
        bt["minutes"] += r["minutes"]
    return {"entries": rows, "total_minutes": total, "total_hours": round(total / 60, 2),
            "by_employee": [{"employee_name": k, "minutes": v} for k, v in sorted(by_employee.items(), key=lambda x: -x[1])],
            "by_ticket": sorted(by_ticket.values(), key=lambda x: -x["minutes"])}


# --- activities feed ----------------------------------------------------------

def activities(store, org: str, ws: str, *, limit: int = 200) -> list[Row]:
    tickets = {t["id"]: t for t in store.list("bl_tickets", organization_id=org, workspace_id=ws)}
    customers = {c["id"]: c["name"] for c in store.list("bl_customers", organization_id=org, workspace_id=ws)}
    employees = {e["id"]: e["name"] for e in store.list("bl_employees", organization_id=org, workspace_id=ws)}
    out: list[Row] = []
    for t in tickets.values():
        out.append({"id": f"t:{t['id']}", "type": "ticket", "at": str(t.get("opened_at") or t.get("created_at")), "ticket_id": t["id"], "ticket_number": t.get("number"),
                    "title": t["title"], "customer_name": customers.get(t["customer_id"], ""), "actor": employees.get(t.get("employee_id") or "", ""),
                    "detail": t.get("description") or "", "minutes": None})
    for te in store.list("bl_time_entries", organization_id=org, workspace_id=ws):
        t = tickets.get(te["ticket_id"])
        if not t:
            continue
        out.append({"id": f"e:{te['id']}", "type": "time_entry", "at": str(te.get("entry_date")), "ticket_id": t["id"], "ticket_number": t.get("number"),
                    "title": t["title"], "customer_name": customers.get(t["customer_id"], ""), "actor": employees.get(te.get("employee_id") or "", ""),
                    "detail": te.get("description") or "", "minutes": int(te.get("minutes") or 0)})
    for u in store.list("bl_external_updates", organization_id=org, workspace_id=ws):
        t = tickets.get(u["ticket_id"])
        if not t:
            continue
        out.append({"id": f"x:{u['id']}", "type": "external_update", "at": str(u.get("update_date")), "ticket_id": t["id"], "ticket_number": t.get("number"),
                    "title": t["title"], "customer_name": customers.get(t["customer_id"], ""), "actor": u.get("contact_name", ""),
                    "detail": u.get("content") or "", "minutes": u.get("minutes")})
    out.sort(key=lambda r: r["at"], reverse=True)
    return out[:limit]


# --- dashboard ----------------------------------------------------------------

def _month_key(v: Any) -> str:
    return str(v or "")[:7]


def overview(store, org: str, ws_ids: list[str], months: int = 6) -> dict[str, Any]:
    today = now().date()
    months_list = []
    y, m = today.year, today.month
    for _ in range(months):
        months_list.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months_list.reverse()
    revenue = {k: 0.0 for k in months_list}
    paid = {k: 0.0 for k in months_list}
    expenses = {k: 0.0 for k in months_list}
    tickets_opened = {k: 0 for k in months_list}
    minutes = {k: 0 for k in months_list}
    open_tickets = 0
    unpaid = 0.0
    unpaid_count = 0
    customers = 0
    resolved_minutes: list[int] = []
    by_product: dict[str, int] = {}
    for ws in ws_ids:
        customers += sum(1 for c in store.list("bl_customers", organization_id=org, workspace_id=ws) if c.get("status", "active") == "active")
        products = {p["id"]: p["name"] for p in store.list("bl_products", organization_id=org, workspace_id=ws)}
        for s in store.list("bl_subscriptions", organization_id=org, workspace_id=ws):
            if s.get("kind", "product") == "product" and not s.get("valid_until"):
                by_product[products.get(s.get("product_id") or "", "?")] = by_product.get(products.get(s.get("product_id") or "", "?"), 0) + int(s.get("user_count") or 0)
        for c in store.list("bl_charges", organization_id=org, workspace_id=ws):
            k = c.get("period", "")
            if c.get("status") == "cancelled":
                continue
            if k in revenue:
                revenue[k] += money(c.get("total"))
                if c.get("status") == "paid":
                    paid[k] += money(c.get("total"))
            if c.get("status") == "issued":
                unpaid += money(c.get("total"))
                unpaid_count += 1
        for e in store.list("bl_expenses", organization_id=org, workspace_id=ws):
            k = _month_key(e.get("expense_date"))
            if k in expenses:
                expenses[k] += money(e.get("amount_ils"))
        tmap = {}
        for t in store.list("bl_tickets", organization_id=org, workspace_id=ws):
            tmap[t["id"]] = t
            k = _month_key(t.get("opened_at"))
            if k in tickets_opened:
                tickets_opened[k] += 1
            if t.get("status") in ("open", "in_progress"):
                open_tickets += 1
        per_ticket: dict[str, int] = {}
        for te in store.list("bl_time_entries", organization_id=org, workspace_id=ws):
            k = _month_key(te.get("entry_date"))
            if k in minutes:
                minutes[k] += int(te.get("minutes") or 0)
            per_ticket[te["ticket_id"]] = per_ticket.get(te["ticket_id"], 0) + int(te.get("minutes") or 0)
        for tid, t in tmap.items():
            if t.get("status") in ("resolved", "closed") and tid in per_ticket:
                resolved_minutes.append(per_ticket[tid])
    cur = months_list[-1]
    return {
        "months": months_list,
        "revenue": [money(revenue[k]) for k in months_list], "paid": [money(paid[k]) for k in months_list],
        "expenses": [money(expenses[k]) for k in months_list], "tickets_opened": [tickets_opened[k] for k in months_list],
        "hours": [round(minutes[k] / 60, 1) for k in months_list],
        "revenue_month": money(revenue[cur]), "expenses_month": money(expenses[cur]), "hours_month": round(minutes[cur] / 60, 1),
        "open_tickets": open_tickets, "unpaid_total": money(unpaid), "unpaid_count": unpaid_count, "customers": customers,
        "avg_resolution_minutes": round(sum(resolved_minutes) / len(resolved_minutes)) if resolved_minutes else 0,
        "users_by_product": [{"name": k, "users": v} for k, v in sorted(by_product.items(), key=lambda x: -x[1])],
    }


# --- external update links ----------------------------------------------------

def _key() -> Optional[bytes]:
    k = os.environ.get("PT_ORG_HMAC_KEY", "") or os.environ.get("CC_SECRET_KEY", "")
    return k.encode() if k else None


def external_token(org: str, ticket_id: str, expires: Optional[date] = None) -> str:
    key = _key()
    if not key:
        raise RuntimeError("PT_ORG_HMAC_KEY is not configured")
    exp = (expires or (now().date() + timedelta(days=90))).isoformat()
    payload = f"{org}|{ticket_id}|{exp}".encode()
    sig = hmac.new(key, payload, hashlib.sha256).digest()[:18]
    return base64.urlsafe_b64encode(payload).decode().rstrip("=") + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def parse_external_token(token: str) -> Optional[tuple[str, str]]:
    """(org, ticket_id) when the signature is valid and the link has not expired."""
    key = _key()
    if not key or "." not in token:
        return None
    body, sig = token.split(".", 1)
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        want = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
    except Exception:
        return None
    if not hmac.compare_digest(hmac.new(key, payload, hashlib.sha256).digest()[:18], want):
        return None
    try:
        org, ticket_id, exp = payload.decode().split("|")
        if date.fromisoformat(exp) < now().date():
            return None
    except ValueError:
        return None
    return org, ticket_id
