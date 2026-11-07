"""Usage metering per client (PRD 9.3, extended).

Every metered call an integration makes on behalf of a client is one usage
entry: provider (claude / gemini / openai / ocr / whatsapp / ...), metric
(requests, tokens_in, tokens_out, messages, recipients, pages, ...), quantity,
the interface that made the call (n8n workflow, bot, app, agent), the client and
optionally the project. Entries come from the workspace reporter token
(``POST /cc/usage``) and from this system's own agent runs. Reports are
aggregated by client, provider, interface and metric for a period.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .service import iso, new_id, now, parse_dt

Row = dict[str, Any]

PROVIDERS = ("claude", "gemini", "openai", "ocr", "whatsapp", "telegram", "sms", "email", "other")
METRICS = ("requests", "tokens_in", "tokens_out", "tokens_cached", "messages", "recipients", "pages", "characters", "minutes", "units")
DEFAULT_UNIT = {"requests": "calls", "tokens_in": "tokens", "tokens_out": "tokens", "tokens_cached": "tokens", "messages": "messages",
                "recipients": "people", "pages": "pages", "characters": "chars", "minutes": "min", "units": "units"}


class UsageEntryIn(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    metric: str = Field(min_length=1, max_length=40)
    quantity: float = Field(ge=0, allow_inf_nan=False)
    interface: str = Field(default="", max_length=160)      # n8n/<workflow>, bot name, app name
    client: Optional[str] = Field(default=None, max_length=160)   # client name (created on first use)
    client_id: Optional[str] = None
    project_id: Optional[str] = None
    model: str = Field(default="", max_length=80)
    unit: str = Field(default="", max_length=20)
    external_id: Optional[str] = Field(default=None, max_length=200)   # de-duplication key
    occurred_at: Optional[str] = None
    recipients: Optional[int] = Field(default=None, ge=0)   # convenience: WhatsApp "to how many people"
    meta: dict[str, Any] = Field(default_factory=dict)


class UsageReportIn(BaseModel):
    workspace_id: str
    entries: list[UsageEntryIn] = Field(min_length=1, max_length=500)


def normalise(e: UsageEntryIn) -> UsageEntryIn:
    e.provider = e.provider.strip().lower()
    e.metric = e.metric.strip().lower()
    if e.metric not in METRICS:
        raise HTTPException(status_code=422, detail=f"metric must be one of {', '.join(METRICS)}")
    if not e.unit:
        e.unit = DEFAULT_UNIT.get(e.metric, "")
    return e


def resolve_client(store, org_id: str, ws: str, *, client_id: Optional[str], name: Optional[str],
                   created: list[str], source: str = "reporter") -> Optional[str]:
    """A client is identified by id, or by name inside the workspace (created on
    first mention so integrations can report before anyone set the client up)."""
    if client_id:
        c = store.get("clients", client_id, organization_id=org_id)
        if not c or c["workspace_id"] != ws:
            raise HTTPException(status_code=422, detail="client not in workspace")
        return client_id
    if not name or not name.strip():
        return None
    name = name.strip()
    for c in store.list("clients", organization_id=org_id, workspace_id=ws):
        if c["name"].lower() == name.lower():
            return c["id"]
    row = store.insert("clients", {"id": new_id("cli"), "organization_id": org_id, "workspace_id": ws, "name": name,
                                   "external_ref": "", "created_at": iso(), "source": source})
    created.append(row["id"])
    return row["id"]


def record(store, org_id: str, ws: str, e: UsageEntryIn, *, client_id: Optional[str], source: str) -> tuple[Optional[Row], bool]:
    """Insert one entry (plus a 'recipients' entry when given). Returns (row, duplicate)."""
    if e.external_id and store.list("usage_entries", organization_id=org_id, workspace_id=ws, external_id=e.external_id):
        return None, True
    when = parse_dt(e.occurred_at) or now()
    base = {"organization_id": org_id, "workspace_id": ws, "project_id": e.project_id, "client_id": client_id,
            "provider": e.provider, "interface": e.interface.strip(), "model": e.model, "occurred_at": iso(when),
            "period_start": when.date().isoformat(), "created_at": iso(), "source": source, "meta": e.meta}
    try:
        row = store.insert("usage_entries", {"id": new_id("use"), "metric": e.metric, "quantity": e.quantity, "unit": e.unit,
                                             "external_id": e.external_id, **base})
    except Exception as exc:  # unique index on (workspace, external_id): concurrent duplicate
        if e.external_id and "unique" in str(exc).lower():
            return None, True
        raise
    if e.recipients is not None and e.metric != "recipients":
        store.insert("usage_entries", {"id": new_id("use"), "metric": "recipients", "quantity": e.recipients, "unit": "people",
                                       "external_id": f"{e.external_id}:recipients" if e.external_id else None, **base})
    return row, False


def _in_window(row: Row, start: Optional[datetime], end: Optional[datetime]) -> bool:
    t = parse_dt(row.get("occurred_at"))
    if t is None:
        return False
    return (start is None or t >= start) and (end is None or t < end)


def summarize(entries: list[Row], clients: dict[str, Row], projects: dict[str, Row]) -> dict[str, Any]:
    """Aggregate usage by client, provider, interface and project."""
    totals: dict[str, float] = {}
    by_client: dict[str, dict] = {}
    by_provider: dict[str, dict] = {}
    by_interface: dict[tuple[str, str], dict] = {}
    by_project: dict[str, dict] = {}

    def add(bucket: dict, metric: str, q: float) -> None:
        bucket[metric] = round(bucket.get(metric, 0.0) + q, 4)

    for r in entries:
        q = float(r.get("quantity") or 0)
        m = r["metric"]
        add(totals, m, q)
        cid = r.get("client_id") or ""
        c = by_client.setdefault(cid, {"client_id": cid or None, "client_name": clients.get(cid, {}).get("name", "") if cid else "ללא לקוח",
                                       "metrics": {}, "providers": {}, "interfaces": {}, "entries": 0})
        add(c["metrics"], m, q)
        add(c["providers"].setdefault(r["provider"], {}), m, q)
        add(c["interfaces"].setdefault(r.get("interface") or "", {}), m, q)
        c["entries"] += 1
        p = by_provider.setdefault(r["provider"], {"provider": r["provider"], "metrics": {}, "entries": 0})
        add(p["metrics"], m, q); p["entries"] += 1
        i = by_interface.setdefault((r.get("interface") or "", r["provider"]), {"interface": r.get("interface") or "", "provider": r["provider"], "metrics": {}, "entries": 0})
        add(i["metrics"], m, q); i["entries"] += 1
        pid = r.get("project_id") or ""
        pr = by_project.setdefault(pid, {"project_id": pid or None, "project_name": projects.get(pid, {}).get("name", "") if pid else "ללא פרויקט", "metrics": {}, "entries": 0})
        add(pr["metrics"], m, q); pr["entries"] += 1

    key = lambda b: -(b["metrics"].get("requests", 0) + b["metrics"].get("messages", 0) + b["metrics"].get("tokens_in", 0) + b["metrics"].get("tokens_out", 0))
    return {
        "totals": totals,
        "by_client": sorted(by_client.values(), key=key),
        "by_provider": sorted(by_provider.values(), key=key),
        "by_interface": sorted(by_interface.values(), key=key),
        "by_project": sorted(by_project.values(), key=key),
        "entries_total": len(entries),
    }


def window(from_: Optional[str], to: Optional[str]) -> tuple[Optional[datetime], Optional[datetime]]:
    """Default period: the current calendar month."""
    start = parse_dt(from_)
    end = parse_dt(to)
    if start is None and end is None:
        t = now()
        start = t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if end is not None and end.hour == 0 and end.minute == 0 and len(str(to or "")) <= 10:
        end = end + timedelta(days=1)   # an inclusive date
    return start, end


def filter_entries(rows: list[Row], *, start, end, client_id: Optional[str], project_id: Optional[str], provider: Optional[str],
                   interface: Optional[str]) -> list[Row]:
    out = []
    for r in rows:
        if not _in_window(r, start, end):
            continue
        if client_id and r.get("client_id") != client_id:
            continue
        if project_id and r.get("project_id") != project_id:
            continue
        if provider and r.get("provider") != provider.lower():
            continue
        if interface and (r.get("interface") or "") != interface:
            continue
        out.append(r)
    return sorted(out, key=lambda r: str(r.get("occurred_at")), reverse=True)
