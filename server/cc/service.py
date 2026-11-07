"""Shared helpers for the Control Center: ids, time, workspace access, audit."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from pt_agent.api.auth import Principal
from pt_agent.models import AuditEvent, Role
from pt_agent.storage import get_store

Row = dict[str, Any]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime] = None) -> str:
    return (dt or now()).isoformat()


def parse_dt(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def audit(p: Principal, action: str, *, detail: str = "", decision: str = "", run_id: str | None = None) -> None:
    get_store().insert("audit_events", AuditEvent(
        organization_id=p.organization_id, run_id=run_id, actor=p.actor, action=action,
        decision=decision, detail=detail[:500],
    ).model_dump(mode="json"))


# --- workspace access (PRD section 6, "גבול הרשאות") -----------------------

WS_ADMIN, WS_EDITOR, WS_VIEWER = "admin", "editor", "viewer"
_RANK = {WS_VIEWER: 0, WS_EDITOR: 1, WS_ADMIN: 2}


def workspace_role(p: Principal, workspace_id: str) -> Optional[str]:
    """The principal's role in a workspace. Organisation admins are workspace
    admins everywhere in their organisation."""
    store = get_store()
    ws = store.get("workspaces", workspace_id, organization_id=p.organization_id)
    if ws is None:
        return None
    if p.role is Role.ORG_ADMIN:
        return WS_ADMIN
    mems = store.list("workspace_members", organization_id=p.organization_id, workspace_id=workspace_id, user_id=p.user_id)
    return mems[0]["role"] if mems else None


def require_workspace(p: Principal, workspace_id: str, minimum: str = WS_VIEWER) -> Row:
    role = workspace_role(p, workspace_id)
    if role is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    if _RANK[role] < _RANK[minimum]:
        raise HTTPException(status_code=403, detail=f"requires workspace {minimum}")
    return get_store().get("workspaces", workspace_id, organization_id=p.organization_id)


def visible_workspace_ids(p: Principal) -> list[str]:
    store = get_store()
    all_ws = store.list("workspaces", organization_id=p.organization_id)
    if p.role is Role.ORG_ADMIN:
        return [w["id"] for w in all_ws]
    mine = {m["workspace_id"] for m in store.list("workspace_members", organization_id=p.organization_id, user_id=p.user_id)}
    return [w["id"] for w in all_ws if w["id"] in mine]


def get_in_workspace(p: Principal, table: str, row_id: str, *, minimum: str = WS_VIEWER) -> Row:
    """Fetch a row and verify the caller may see its workspace."""
    row = get_store().get(table, row_id, organization_id=p.organization_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    ws_id = row.get("workspace_id")
    if ws_id is None and table == "project_assets":
        proj = get_store().get("cc_projects", row["project_id"], organization_id=p.organization_id)
        ws_id = proj["workspace_id"] if proj else None
    if ws_id:
        require_workspace(p, ws_id, minimum)
    return row


def active_links(store, organization_id: str, **filters: Any) -> list[Row]:
    """project_assets rows that are still in force. An unassigned link is kept
    (source='removed') for history but must never count as an assignment."""
    return [pa for pa in store.list("project_assets", organization_id=organization_id, **filters)
            if pa.get("source") != "removed"]


def assignment_index(store, organization_id: str) -> dict[str, str]:
    return {pa["asset_id"]: pa["project_id"] for pa in active_links(store, organization_id)}


SECRET_FIELDS = {"secret_enc", "report_token", "report_token_hash"}


def public(row: Row) -> Row:
    """Row without server-side secrets (encrypted tokens, report-token hash)."""
    return {k: v for k, v in row.items() if k not in SECRET_FIELDS}


def list_in_workspaces(p: Principal, table: str, workspace_id: Optional[str] = None, **filters: Any) -> list[Row]:
    store = get_store()
    ids = [workspace_id] if workspace_id else visible_workspace_ids(p)
    if workspace_id and workspace_id not in visible_workspace_ids(p):
        raise HTTPException(status_code=404, detail="workspace not found")
    out: list[Row] = []
    for ws in ids:
        out.extend(store.list(table, organization_id=p.organization_id, workspace_id=ws, **filters))
    return out
