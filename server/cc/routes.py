"""Control Center HTTP API (PRD sections 3-9). Mounted at /cc."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from pt_agent.api.auth import Principal, current_principal
from pt_agent.models import Role
from pt_agent.storage import get_store

from . import agents as agent_engine
from . import profile as profile_engine
from . import sync as sync_engine
from . import usage as usage_engine
from .connectors import PROVIDERS, ConfigError, ConnectorError, build, validate_config
from .secrets import SecretsUnavailable, decrypt, encrypt, mask
from .service import (
    WS_ADMIN,
    WS_EDITOR,
    WS_VIEWER,
    active_links,
    assignment_index,
    audit,
    get_in_workspace,
    iso,
    list_in_workspaces,
    new_id,
    now,
    parse_dt,
    public,
    require_workspace,
    visible_workspace_ids,
)

# Connection statuses the scheduler keeps retrying. 'error' is a transient
# provider/network failure; 'disconnected' is only ever set by a user.
RETRYABLE = ("ok", "partial", "new", "rate_limited", "error")


def _month(c: Row) -> str:
    """Billing month of a cost entry; entries logged without a period count in
    the month they were recorded."""
    return str(c.get("period_start") or c.get("created_at") or "")[:7]


def _latest_production(events: list[Row]) -> Optional[Row]:
    """Newest production event (events are newest-first). A project is 'failing
    in production' only while its latest production event is a failure."""
    return next((e for e in events if e.get("environment") == "production"), None)

router = APIRouter(prefix="/cc", tags=["control-center"])
Row = dict[str, Any]


def _store():
    return get_store()


# --- Workspaces -------------------------------------------------------------

class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = "personal"


@router.get("/workspaces")
def list_workspaces(p: Principal = Depends(current_principal)):
    ids = visible_workspace_ids(p)
    return [public(w) for w in _store().list("workspaces", organization_id=p.organization_id) if w["id"] in ids]


@router.post("/workspaces")
def create_workspace(body: WorkspaceIn, p: Principal = Depends(current_principal)):
    if p.role not in (Role.ORG_ADMIN, Role.SURVEY_MANAGER):
        raise HTTPException(status_code=403, detail="organisation admin required")
    ws = {"id": new_id("ws"), "organization_id": p.organization_id, "name": body.name, "kind": body.kind, "created_at": iso()}
    _store().insert("workspaces", ws)
    _store().insert("workspace_members", {"id": new_id("wsm"), "organization_id": p.organization_id, "workspace_id": ws["id"],
                                          "user_id": p.user_id, "role": WS_ADMIN, "created_at": iso()})
    audit(p, "cc.workspace.create", detail=ws["id"])
    return ws


class MemberIn(BaseModel):
    user_id: str
    role: str = WS_VIEWER


@router.get("/workspaces/{ws_id}/members")
def list_members(ws_id: str, p: Principal = Depends(current_principal)):
    require_workspace(p, ws_id)
    mems = _store().list("workspace_members", organization_id=p.organization_id, workspace_id=ws_id)
    users = {u["id"]: u for u in _store().list("users", organization_id=p.organization_id)}
    return [{**m, "email": users.get(m["user_id"], {}).get("email", ""), "display_name": users.get(m["user_id"], {}).get("display_name", "")} for m in mems]


@router.post("/workspaces/{ws_id}/members")
def add_member(ws_id: str, body: MemberIn, p: Principal = Depends(current_principal)):
    require_workspace(p, ws_id, WS_ADMIN)
    if body.role not in (WS_ADMIN, WS_EDITOR, WS_VIEWER):
        raise HTTPException(status_code=422, detail="role must be admin|editor|viewer")
    if not _store().get("users", body.user_id, organization_id=p.organization_id):
        raise HTTPException(status_code=404, detail="user not found")
    existing = _store().list("workspace_members", organization_id=p.organization_id, workspace_id=ws_id, user_id=body.user_id)
    if existing:
        return _store().update("workspace_members", existing[0]["id"], organization_id=p.organization_id, patch={"role": body.role})
    row = {"id": new_id("wsm"), "organization_id": p.organization_id, "workspace_id": ws_id, "user_id": body.user_id, "role": body.role, "created_at": iso()}
    _store().insert("workspace_members", row)
    audit(p, "cc.workspace.member", detail=f"{ws_id} {body.user_id} {body.role}")
    return row


# --- Overview (PRD section 3 "סקירה") --------------------------------------

@router.get("/overview")
def overview(workspace_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    store = _store()
    org = p.organization_id
    ws_ids = [workspace_id] if workspace_id else visible_workspace_ids(p)
    if workspace_id and workspace_id not in visible_workspace_ids(p):
        raise HTTPException(status_code=404, detail="workspace not found")
    projects = list_in_workspaces(p, "cc_projects", workspace_id)
    assets = [a for a in list_in_workspaces(p, "cc_assets", workspace_id) if not a.get("removed_at")]
    sessions = list_in_workspaces(p, "work_sessions", workspace_id)
    connections = list_in_workspaces(p, "connections", workspace_id)
    inbox = [i for i in list_in_workspaces(p, "inbox_items", workspace_id) if i["status"] == "open"]
    alerts = [a for a in list_in_workspaces(p, "alerts", workspace_id) if a["status"] == "open"]
    events = sorted(list_in_workspaces(p, "activity_events", workspace_id), key=lambda e: str(e.get("occurred_at")), reverse=True)
    sync_engine.check_sync_delays(store, org, ws_ids)

    by_kind: dict[str, int] = {}
    for a in assets:
        by_kind[a["kind"]] = by_kind.get(a["kind"], 0) + 1
    links = active_links(store, org)
    assigned = {pa["asset_id"] for pa in links}
    link_count: dict[str, int] = {}
    for pa in links:
        link_count[pa["project_id"]] = link_count.get(pa["project_id"], 0) + 1
    pid_name = {x["id"]: x["name"] for x in projects}

    def project_state(pr: Row) -> dict:
        pev = [e for e in events if e.get("project_id") == pr["id"]]
        last_prod = _latest_production(pev)
        prod_fail = last_prod if last_prod and last_prod["result"] == "failure" else None
        last_sess = next((s for s in sorted(sessions, key=lambda s: str(s.get("started_at")), reverse=True) if s["project_id"] == pr["id"]), None)
        tone = "bad" if prod_fail else ("warn" if any(e["result"] == "failure" for e in pev[:10]) else "ok")
        return {**pr, "tone": tone, "last_failure": prod_fail or next((e for e in pev if e["result"] == "failure"), None),
                "last_session": last_sess, "asset_count": link_count.get(pr["id"], 0)}

    return {
        "projects": [project_state(x) for x in projects],
        "assets_by_kind": by_kind, "assets_total": len(assets), "unassigned": sum(1 for a in assets if a["id"] not in assigned),
        "open_sessions": [s for s in sessions if s["status"] == "open"][-10:],
        "critical_alerts": alerts[-20:],
        "inbox_open": len(inbox),
        "connections": [{**c, "freshness": sync_engine.freshness(c), "secret_enc": None} for c in connections],
        "recent_events": [{**e, "project_name": pid_name.get(e.get("project_id") or "", "")} for e in events[:20]],
    }


# --- Projects (PRD sections 3, 9.1) ----------------------------------------

class ProjectIn(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    owner: str = ""
    importance: str = "normal"
    environment: str = "unclassified"
    budget_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    client_id: Optional[str] = None


class ProjectPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    importance: Optional[str] = None
    status: Optional[str] = None
    environment: Optional[str] = None
    budget_usd: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    default_key_id: Optional[str] = None     # "" clears the default key
    client_id: Optional[str] = None          # "" clears the client


def _check_client(p: Principal, client_id: Optional[str], workspace_id: str) -> None:
    if client_id:
        c = _store().get("clients", client_id, organization_id=p.organization_id)
        if not c or c["workspace_id"] != workspace_id:
            raise HTTPException(status_code=422, detail="client must belong to the project's workspace")


@router.get("/projects")
def list_projects(workspace_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    return list_in_workspaces(p, "cc_projects", workspace_id)


@router.post("/projects")
def create_project(body: ProjectIn, p: Principal = Depends(current_principal)):
    require_workspace(p, body.workspace_id, WS_EDITOR)
    _check_client(p, body.client_id, body.workspace_id)
    row = {"id": new_id("prj"), "organization_id": p.organization_id, "created_at": iso(), "status": "active", **body.model_dump()}
    _store().insert("cc_projects", row)
    audit(p, "cc.project.create", detail=row["id"])
    return row


@router.get("/projects/{project_id}")
def get_project(project_id: str, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    pr = get_in_workspace(p, "cc_projects", project_id)
    links = active_links(store, org, project_id=project_id)
    assets = [{**a, "link_source": l["source"]} for l in links for a in [store.get("cc_assets", l["asset_id"], organization_id=org)] if a]
    events = sorted(store.list("activity_events", organization_id=org, workspace_id=pr["workspace_id"], project_id=project_id),
                    key=lambda e: str(e.get("occurred_at")), reverse=True)[:50]
    sessions = store.list("work_sessions", organization_id=org, workspace_id=pr["workspace_id"], project_id=project_id)
    costs = store.list("cost_entries", organization_id=org, workspace_id=pr["workspace_id"], project_id=project_id)
    agents = [a for a in store.list("cc_agents", organization_id=org, workspace_id=pr["workspace_id"])
              if a.get("project_id") in (None, "", project_id)]
    runs = store.list("agent_runs", organization_id=org, workspace_id=pr["workspace_id"], project_id=project_id)
    conns = {c["id"]: public(c) for c in store.list("connections", organization_id=org, workspace_id=pr["workspace_id"])}
    keys = [public(k_) for k_ in store.list("provider_keys", organization_id=org, workspace_id=pr["workspace_id"])]
    pt_projects = [x for x in store.list("projects", organization_id=org) if x.get("cc_project_id") == project_id]
    month_cost = sum(float(c.get("amount") or 0) for c in costs if _month(c) == now().strftime("%Y-%m"))
    client = store.get("clients", pr["client_id"], organization_id=org) if pr.get("client_id") else None
    start, end = usage_engine.window(None, None)
    usage_rows = usage_engine.filter_entries(store.list("usage_entries", organization_id=org, workspace_id=pr["workspace_id"], project_id=project_id),
                                             start=start, end=end, client_id=None, project_id=None, provider=None, interface=None)
    usage = usage_engine.summarize(usage_rows, {client["id"]: client} if client else {}, {pr["id"]: pr})
    scans = sorted(store.list("project_scans", organization_id=org, project_id=project_id), key=lambda s: str(s.get("created_at")), reverse=True)
    return {"project": pr, "assets": assets, "events": events, "sessions": sessions, "costs": costs,
            "cost_month_usd": round(month_cost, 2), "agents": agents, "runs": runs,
            "connections": [conns[a["connection_id"]] for a in assets if a.get("connection_id") in conns and conns] if conns else [],
            "keys": keys, "pt_projects": pt_projects, "client": client,
            "usage_month": {"totals": usage["totals"], "by_provider": usage["by_provider"], "by_interface": usage["by_interface"]},
            "profile": {"summary": pr.get("profile_summary"), "at": pr.get("profile_at"),
                        "assets": [{"id": a["id"], "name": a["name"], "provider": a["provider"], "kind": a["kind"], "profile": a.get("profile")} for a in assets]},
            "scans": [{k: v for k, v in s.items() if k != "findings"} for s in scans[:10]],
            "last_scan": scans[0] if scans else None}


@router.post("/projects/{project_id}/profile")
def refresh_profile(project_id: str, p: Principal = Depends(current_principal)):
    """Rebuild 'how is it built' for every asset of the project (read-only
    provider calls through the workspace connections)."""
    pr = get_in_workspace(p, "cc_projects", project_id, minimum=WS_EDITOR)
    out = profile_engine.build_profile(_store(), p.organization_id, pr)
    audit(p, "cc.project.profile", detail=f"{project_id} {len(out['assets'])} assets")
    return out


@router.post("/projects/{project_id}/scan")
def scan_project(project_id: str, kind: str = "health", p: Principal = Depends(current_principal)):
    """kind=health: deterministic findings from GitHub / Vercel / Supabase metadata.
    kind=code: Claude reviews the repositories' most relevant source files."""
    pr = get_in_workspace(p, "cc_projects", project_id, minimum=WS_EDITOR)
    if kind == "code":
        try:
            row = profile_engine.run_code_scan(_store(), p.organization_id, pr, actor=p.actor)
        except ConnectorError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    elif kind == "health":
        row = profile_engine.run_scan(_store(), p.organization_id, pr, actor=p.actor)
    else:
        raise HTTPException(status_code=422, detail="kind must be health|code")
    audit(p, "cc.project.scan", decision=row.get("grade") or row["status"], detail=f"{project_id} {kind} {row['id']} {row['counts']}")
    if row.get("grade") == "C":
        from . import notify
        notify.send(store=_store(), org_id=p.organization_id, workspace_id=pr["workspace_id"], kind="scan",
                    title=f"סריקת {kind} של {pr['name']}: ציון C", message=f"{row['counts']} · {row.get('summary', {}).get('text', '')[:300]}")
    return row


@router.get("/projects/{project_id}/scans")
def list_scans(project_id: str, p: Principal = Depends(current_principal)):
    get_in_workspace(p, "cc_projects", project_id)
    return sorted(_store().list("project_scans", organization_id=p.organization_id, project_id=project_id), key=lambda s: str(s.get("created_at")), reverse=True)


@router.get("/scans/{scan_id}")
def get_scan(scan_id: str, p: Principal = Depends(current_principal)):
    return get_in_workspace(p, "project_scans", scan_id)


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: ProjectPatch, p: Principal = Depends(current_principal)):
    pr = get_in_workspace(p, "cc_projects", project_id, minimum=WS_EDITOR)
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "status" in patch and patch["status"] not in ("active", "archived"):
        raise HTTPException(status_code=422, detail="status must be active|archived")
    if patch.get("client_id"):
        _check_client(p, patch["client_id"], pr["workspace_id"])
    if "default_key_id" in patch and patch["default_key_id"]:
        k = _store().get("provider_keys", patch["default_key_id"], organization_id=p.organization_id)
        if not k or k["workspace_id"] != pr["workspace_id"]:
            raise HTTPException(status_code=422, detail="key must belong to the project's workspace")
    row = _store().update("cc_projects", project_id, organization_id=p.organization_id, patch=patch)
    audit(p, "cc.project.update", detail=f"{project_id} {','.join(patch)}")
    return row


class AssignIn(BaseModel):
    asset_id: str


@router.post("/projects/{project_id}/assets")
def assign_asset(project_id: str, body: AssignIn, p: Principal = Depends(current_principal)):
    pr = get_in_workspace(p, "cc_projects", project_id, minimum=WS_EDITOR)
    asset = get_in_workspace(p, "cc_assets", body.asset_id)
    if asset["workspace_id"] != pr["workspace_id"]:
        raise HTTPException(status_code=422, detail="asset and project must share a workspace")   # PRD 4.4
    store, org = _store(), p.organization_id
    existing = store.list("project_assets", organization_id=org, project_id=project_id, asset_id=body.asset_id)
    if not existing:
        store.insert("project_assets", {"id": new_id("pa"), "organization_id": org, "project_id": project_id,
                                        "asset_id": body.asset_id, "source": "manual", "created_at": iso()})
    else:
        # A link that was unassigned earlier is re-activated rather than duplicated
        # (the DB key is unique on project + asset).
        for l in existing:
            if l.get("source") == "removed":
                store.update("project_assets", l["id"], organization_id=org, patch={"source": "manual", "created_at": iso()})
    events = store.list("activity_events", organization_id=org, workspace_id=pr["workspace_id"], asset_id=body.asset_id)
    for e in events:
        if not e.get("project_id"):
            store.update("activity_events", e["id"], organization_id=org, patch={"project_id": project_id})
    # The asset now has an owner: a current production failure becomes an alert.
    latest = _latest_production(sorted(events, key=lambda e: str(e.get("occurred_at")), reverse=True))
    if latest and latest.get("result") == "failure":
        sync_engine._alert(store, org, pr["workspace_id"], "failure", "asset", body.asset_id,
                           f"כשל בייצור: {latest.get('title', '')}"[:200], occurred_at=latest.get("occurred_at"))
    for i in store.list("inbox_items", organization_id=org, workspace_id=pr["workspace_id"], asset_id=body.asset_id, status="open"):
        store.update("inbox_items", i["id"], organization_id=org, patch={"status": "resolved", "resolved_project_id": project_id})
    audit(p, "cc.asset.assign", detail=f"{body.asset_id} -> {project_id}")
    return {"ok": True}


@router.delete("/projects/{project_id}/assets/{asset_id}")
def unassign_asset(project_id: str, asset_id: str, p: Principal = Depends(current_principal)):
    get_in_workspace(p, "cc_projects", project_id, minimum=WS_EDITOR)
    store, org = _store(), p.organization_id
    for l in store.list("project_assets", organization_id=org, project_id=project_id, asset_id=asset_id):
        store.update("project_assets", l["id"], organization_id=org, patch={"source": "removed"})
    audit(p, "cc.asset.unassign", detail=f"{asset_id} x {project_id}")
    return {"ok": True}


# --- Connections (PRD section 4) --------------------------------------------

class ConnectionIn(BaseModel):
    workspace_id: str
    provider: str
    account_label: str = ""
    secret: str = Field(min_length=4)
    config: dict[str, Any] = Field(default_factory=dict)


@router.get("/providers")
def providers():
    return PROVIDERS


@router.get("/connections")
def list_connections(workspace_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    return [{**{k: v for k, v in c.items() if k != "secret_enc"}, "freshness": sync_engine.freshness(c)}
            for c in list_in_workspaces(p, "connections", workspace_id)]


@router.post("/connections")
def create_connection(body: ConnectionIn, p: Principal = Depends(current_principal)):
    require_workspace(p, body.workspace_id, WS_ADMIN)
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=422, detail="unknown provider")
    try:
        validate_config(body.provider, body.config)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    try:
        enc = encrypt(body.secret)
    except SecretsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    # Verify access before saving (PRD 4.1).
    try:
        info = build(body.provider, body.secret, body.config).verify()
        status = "ok"
    except ConnectorError as exc:
        info, status = {"error": str(exc)}, exc.status
    except Exception as exc:
        info, status = {"error": f"{type(exc).__name__}: {exc}"[:200]}, "disconnected"
    row = {"id": new_id("con"), "organization_id": p.organization_id, "workspace_id": body.workspace_id,
           "provider": body.provider, "account_label": body.account_label or info.get("account", ""), "status": status,
           "last_error": info.get("error", ""), "created_at": iso(), "secret_enc": enc, "secret_masked": mask(body.secret),
           "config": body.config, "capabilities": info.get("capabilities", []), "verify": {k: v for k, v in info.items() if k != "error"}}
    _store().insert("connections", row)
    audit(p, "cc.connection.create", detail=f"{row['id']} {body.provider} {status}")
    return public(row)


class ConnectionPatch(BaseModel):
    account_label: Optional[str] = None
    secret: Optional[str] = None
    config: Optional[dict[str, Any]] = None


@router.patch("/connections/{conn_id}")
def update_connection(conn_id: str, body: ConnectionPatch, p: Principal = Depends(current_principal)):
    c = get_in_workspace(p, "connections", conn_id, minimum=WS_ADMIN)
    patch: dict[str, Any] = {}
    if body.account_label is not None:
        patch["account_label"] = body.account_label
    if body.config is not None:
        try:
            validate_config(c["provider"], body.config)
        except ConfigError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        old_target = (c.get("config") or {}).get("base_url", "")
        if body.config.get("base_url", "") != old_target and not body.secret:
            # The stored key would otherwise be sent to the new host on the next
            # sync; changing the destination requires re-entering the secret.
            raise HTTPException(status_code=422, detail="changing base_url requires re-entering the secret")
        patch["config"] = body.config
    if body.secret:
        try:
            patch["secret_enc"] = encrypt(body.secret); patch["secret_masked"] = mask(body.secret); patch["status"] = "new"
        except SecretsUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    row = _store().update("connections", conn_id, organization_id=p.organization_id, patch=patch)
    audit(p, "cc.connection.update", detail=f"{conn_id} {','.join(patch)}")
    return public(row)


@router.post("/connections/{conn_id}/sync")
def sync_connection(conn_id: str, p: Principal = Depends(current_principal)):
    c = get_in_workspace(p, "connections", conn_id, minimum=WS_EDITOR)
    summary = sync_engine.run_connection_sync(_store(), p.organization_id, c, actor=p.actor)
    audit(p, "cc.connection.sync", decision=summary["status"], detail=f"{conn_id} {summary}")
    return summary


@router.post("/connections/{conn_id}/disconnect")
def disconnect(conn_id: str, p: Principal = Depends(current_principal)):
    get_in_workspace(p, "connections", conn_id, minimum=WS_ADMIN)
    row = _store().update("connections", conn_id, organization_id=p.organization_id,
                          patch={"status": "disconnected", "secret_enc": "", "secret_masked": ""})
    audit(p, "cc.connection.disconnect", detail=conn_id)
    return public(row)


@router.get("/sync/all")
def sync_all(authorization: Optional[str] = Header(default=None)):
    """Scheduled sync (Vercel cron). Protected by CRON_SECRET; no user context."""
    secret = os.environ.get("CRON_SECRET", "")
    if not secret or not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(status_code=401, detail="cron secret required")
    store = _store()
    out = []
    for org in store.list_organization_ids():
        for ws in store.list("workspaces", organization_id=org):
            for c in store.list("connections", organization_id=org, workspace_id=ws["id"]):
                if c["status"] in RETRYABLE and c.get("secret_enc"):
                    out.append({"connection": c["id"], **sync_engine.run_connection_sync(store, org, c)})
            sync_engine.check_sync_delays(store, org, [ws["id"]])
    return {"synced": out}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _workspace_by_token(store, workspace_id: str, token: str) -> Optional[Row]:
    """Resolve the workspace an external reporter signs for. Only a hash of the
    token is stored; the comparison is constant-time."""
    if not token:
        return None
    for org in store.list_organization_ids():
        for w in store.list("workspaces", organization_id=org):
            if w["id"] != workspace_id:
                continue
            stored = w.get("report_token_hash") or ""
            if stored and hmac.compare_digest(stored, _token_hash(token)):
                return w
            return None
    return None


# --- Assets & inbox (PRD sections 3, 4) ------------------------------------

@router.get("/assets")
def list_assets(workspace_id: Optional[str] = None, include_removed: bool = False, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    rows = list_in_workspaces(p, "cc_assets", workspace_id)
    links: dict[str, list[str]] = {}
    for pa in active_links(store, org):
        links.setdefault(pa["asset_id"], []).append(pa["project_id"])
    out = []
    for a in rows:
        if a.get("removed_at") and not include_removed:
            continue
        out.append({**a, "project_ids": links.get(a["id"], [])})
    return out


class AssetPatch(BaseModel):
    description: Optional[str] = None
    environment: Optional[str] = None
    importance: Optional[str] = None
    shared: Optional[bool] = None


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    a = get_in_workspace(p, "cc_assets", asset_id)
    links = active_links(store, org, asset_id=asset_id)
    events = sorted(store.list("activity_events", organization_id=org, workspace_id=a["workspace_id"], asset_id=asset_id),
                    key=lambda e: str(e.get("occurred_at")), reverse=True)[:30]
    conn = store.get("connections", a["connection_id"], organization_id=org) if a.get("connection_id") else None
    return {"asset": a, "projects": [store.get("cc_projects", l["project_id"], organization_id=org) for l in links],
            "events": events, "connection": public(conn) if conn else None}


@router.patch("/assets/{asset_id}")
def patch_asset(asset_id: str, body: AssetPatch, p: Principal = Depends(current_principal)):
    get_in_workspace(p, "cc_assets", asset_id, minimum=WS_EDITOR)
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "description" in patch:
        patch["description_manual"] = True   # survives the next sync (PRD 4.4)
    row = _store().update("cc_assets", asset_id, organization_id=p.organization_id, patch=patch)
    audit(p, "cc.asset.update", detail=f"{asset_id} {','.join(patch)}")
    return row


class SourceActionIn(BaseModel):
    action: str                      # archive | delete
    confirm: str = ""                # the asset's full name, typed by the admin


@router.post("/assets/{asset_id}/source-action")
def asset_source_action(asset_id: str, body: SourceActionIn, p: Principal = Depends(current_principal)):
    """Act on the asset *at its provider* (archive or delete a GitHub repository).
    Destructive by design, so: workspace admin only, the full name must be typed
    back, the connection's token must have administration rights, and the
    action is written to the audit log before and after."""
    store, org = _store(), p.organization_id
    a = get_in_workspace(p, "cc_assets", asset_id, minimum=WS_ADMIN)
    if body.action not in ("archive", "delete"):
        raise HTTPException(status_code=422, detail="action must be archive|delete")
    supported = {("github", "repo"), ("vercel", "vercel_project"), ("supabase", "supabase_project")}
    if (a["provider"], a["kind"]) not in supported:
        raise HTTPException(status_code=422, detail="source actions are supported for GitHub repositories, Vercel projects and Supabase projects")
    if body.confirm.strip().lower() != a["name"].strip().lower():
        raise HTTPException(status_code=422, detail="type the asset's full name to confirm")
    conn = store.get("connections", a["connection_id"], organization_id=org) if a.get("connection_id") else None
    if not conn or not conn.get("secret_enc"):
        # fall back to any live connection of the provider in the workspace
        conn = next((c for c in store.list("connections", organization_id=org, workspace_id=a["workspace_id"], provider=a["provider"])
                     if c.get("secret_enc") and c["status"] != "disconnected"), None)
    if not conn or not conn.get("secret_enc"):
        raise HTTPException(status_code=409, detail=f"no live {a['provider']} connection with a token in this workspace")
    try:
        secret = decrypt(conn["secret_enc"])
    except SecretsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    audit(p, f"cc.asset.source_{body.action}", decision="requested", detail=f"{asset_id} {a['name']}")
    connector = build(a["provider"], secret, conn.get("config") or {})
    try:
        if a["provider"] == "github":
            result = connector.delete_repository(a["name"]) if body.action == "delete" else connector.archive_repository(a["name"])
        else:   # vercel / supabase: 'archive' means pause (reversible from the provider's dashboard)
            result = connector.delete_project(a["external_id"]) if body.action == "delete" else connector.pause_project(a["external_id"])
    except ConnectorError as exc:
        audit(p, f"cc.asset.source_{body.action}", decision="failed", detail=f"{asset_id} {exc}")
        raise HTTPException(status_code=409, detail=str(exc))
    if body.action == "delete":
        row = store.update("cc_assets", asset_id, organization_id=org, patch={"removed_at": iso(), "state": "deleted", "deleted_by": p.actor})
        for i in store.list("inbox_items", organization_id=org, workspace_id=a["workspace_id"], asset_id=asset_id, status="open"):
            store.update("inbox_items", i["id"], organization_id=org, patch={"status": "resolved"})
    else:
        row = store.update("cc_assets", asset_id, organization_id=org, patch={"state": "archived" if a["provider"] == "github" else "paused", "archived_by": p.actor})
    audit(p, f"cc.asset.source_{body.action}", decision="ok", detail=f"{asset_id} {a['name']}")
    return {"ok": True, "action": body.action, "asset": row, **result}


@router.get("/inbox")
def list_inbox(workspace_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    items = [i for i in list_in_workspaces(p, "inbox_items", workspace_id) if i["status"] == "open"]
    return [{**i, "asset": store.get("cc_assets", i["asset_id"], organization_id=org) if i.get("asset_id") else None} for i in items]


class InboxAction(BaseModel):
    action: str                      # assign | dismiss | create_project | mark_shared
    project_id: Optional[str] = None
    project_name: Optional[str] = None


@router.post("/inbox/{item_id}")
def act_inbox(item_id: str, body: InboxAction, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    item = get_in_workspace(p, "inbox_items", item_id, minimum=WS_EDITOR)
    if body.action == "dismiss":
        store.update("inbox_items", item_id, organization_id=org, patch={"status": "dismissed"})
        audit(p, "cc.inbox.dismiss", detail=item_id)
        return {"ok": True}
    project_id = body.project_id
    if body.action == "create_project":
        if not body.project_name:
            raise HTTPException(status_code=422, detail="project_name required")
        pr = {"id": new_id("prj"), "organization_id": org, "workspace_id": item["workspace_id"], "name": body.project_name,
              "owner": p.display_name or p.email, "importance": "normal", "status": "active", "environment": "unclassified",
              "created_at": iso(), "description": ""}
        store.insert("cc_projects", pr)
        project_id = pr["id"]
    if body.action in ("assign", "create_project"):
        if not project_id or not item.get("asset_id"):
            raise HTTPException(status_code=422, detail="project_id required")
        assign_asset(project_id, AssignIn(asset_id=item["asset_id"]), p)
        return {"ok": True, "project_id": project_id}
    if body.action == "mark_shared":
        if item.get("asset_id"):
            store.update("cc_assets", item["asset_id"], organization_id=org, patch={"shared": True})
        store.update("inbox_items", item_id, organization_id=org, patch={"status": "resolved"})
        return {"ok": True}
    raise HTTPException(status_code=422, detail="unknown action")


# --- Sessions (PRD section 2 "מחזור חיים של סשן") --------------------------

class SessionIn(BaseModel):
    project_id: str
    title: str = Field(min_length=1, max_length=160)
    goal: str = ""
    owner: str = ""
    tool: str = "manual"


class SessionPatch(BaseModel):
    status: Optional[str] = None
    outcome: Optional[str] = None
    links: Optional[list[str]] = None
    follow_up: Optional[str] = None
    title: Optional[str] = None
    goal: Optional[str] = None


@router.get("/sessions")
def list_sessions(workspace_id: Optional[str] = None, status: Optional[str] = None, p: Principal = Depends(current_principal)):
    rows = list_in_workspaces(p, "work_sessions", workspace_id)
    if status:
        rows = [r for r in rows if r["status"] == status]
    stale_after = now() - timedelta(days=int(os.environ.get("CC_SESSION_IDLE_DAYS", "7")))
    store, org = _store(), p.organization_id
    out = []
    for s in rows:
        ev = store.list("activity_events", organization_id=org, workspace_id=s["workspace_id"], session_id=s["id"])
        last = max([parse_dt(e.get("occurred_at")) for e in ev] + [parse_dt(s.get("started_at"))], key=lambda d: d or now())
        out.append({**s, "event_count": len(ev), "last_activity_at": iso(last) if last else None,
                    "idle": s["status"] in ("open", "waiting") and bool(last) and last < stale_after})
    return sorted(out, key=lambda s: str(s.get("started_at")), reverse=True)


@router.post("/sessions")
def create_session(body: SessionIn, p: Principal = Depends(current_principal)):
    pr = get_in_workspace(p, "cc_projects", body.project_id, minimum=WS_EDITOR)
    row = {"id": new_id("ses"), "organization_id": p.organization_id, "workspace_id": pr["workspace_id"], "status": "open",
           "started_at": iso(), "created_at": iso(), "owner": body.owner or (p.display_name or p.email), **body.model_dump(exclude={"owner"})}
    _store().insert("work_sessions", row)
    audit(p, "cc.session.create", detail=row["id"])
    return row


@router.get("/sessions/{session_id}")
def get_session(session_id: str, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    s = get_in_workspace(p, "work_sessions", session_id)
    events = sorted(store.list("activity_events", organization_id=org, workspace_id=s["workspace_id"], session_id=session_id),
                    key=lambda e: str(e.get("occurred_at")), reverse=True)
    # Suggestions (PRD 2.3): unlinked project events since the session started, or
    # from the last 7 days, are *proposed*; nothing is linked by time alone.
    start = parse_dt(s.get("started_at")) or now()
    floor = min(start, now() - timedelta(days=7))
    suggestions = sorted([e for e in store.list("activity_events", organization_id=org, workspace_id=s["workspace_id"], project_id=s["project_id"])
                          if not e.get("session_id") and (parse_dt(e.get("occurred_at")) or now()) >= floor],
                         key=lambda e: str(e.get("occurred_at")), reverse=True)[:20]
    runs = store.list("agent_runs", organization_id=org, workspace_id=s["workspace_id"], session_id=session_id)
    return {"session": s, "project": store.get("cc_projects", s["project_id"], organization_id=org), "events": events,
            "suggested_events": suggestions, "runs": runs}


@router.patch("/sessions/{session_id}")
def patch_session(session_id: str, body: SessionPatch, p: Principal = Depends(current_principal)):
    s = get_in_workspace(p, "work_sessions", session_id, minimum=WS_EDITOR)
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "status" in patch:
        if patch["status"] not in ("open", "waiting", "done", "cancelled"):
            raise HTTPException(status_code=422, detail="bad status")
        patch["ended_at"] = iso() if patch["status"] in ("done", "cancelled") else None
    row = _store().update("work_sessions", session_id, organization_id=p.organization_id, patch=patch)
    audit(p, "cc.session.update", detail=f"{session_id} {','.join(patch)}")
    return row


class LinkEventIn(BaseModel):
    event_id: str


@router.post("/sessions/{session_id}/events")
def link_event(session_id: str, body: LinkEventIn, p: Principal = Depends(current_principal)):
    s = get_in_workspace(p, "work_sessions", session_id, minimum=WS_EDITOR)
    e = get_in_workspace(p, "activity_events", body.event_id)
    if e["workspace_id"] != s["workspace_id"]:
        raise HTTPException(status_code=422, detail="cross-workspace link refused")
    _store().update("activity_events", body.event_id, organization_id=p.organization_id,
                    patch={"session_id": session_id, "project_id": s["project_id"]})
    audit(p, "cc.session.link", detail=f"{session_id} <- {body.event_id}")
    return {"ok": True}


# --- Activity feed -----------------------------------------------------------

@router.get("/events")
def list_events(workspace_id: Optional[str] = None, project_id: Optional[str] = None, limit: int = Query(default=100, le=500),
                p: Principal = Depends(current_principal)):
    f = {"project_id": project_id} if project_id else {}
    rows = list_in_workspaces(p, "activity_events", workspace_id, **f)
    return sorted(rows, key=lambda e: str(e.get("occurred_at")), reverse=True)[:limit]


class ReportIn(BaseModel):
    """External reporter (private service / cron / local bot), PRD section 4."""
    workspace_id: str
    service: str
    external_id: str
    kind: str = "heartbeat"
    result: str = "success"
    environment: str = "production"
    title: str = ""
    url: str = ""
    occurred_at: Optional[str] = None


@router.post("/report")
def external_report(body: ReportIn, x_report_token: Optional[str] = Header(default=None)):
    """Signed external report: token per workspace (data.report_token). Replays are
    recognised as duplicates via the unique external_id."""
    store = _store()
    ws = _workspace_by_token(store, body.workspace_id, x_report_token or "")
    if not ws:
        raise HTTPException(status_code=401, detail="invalid report token")
    org = ws["organization_id"]
    ext = f"service:{body.service}"
    assets = [a for a in store.list("cc_assets", organization_id=org, workspace_id=ws["id"], provider="reporter") if a["external_id"] == ext]
    if assets:
        asset = store.update("cc_assets", assets[0]["id"], organization_id=org, patch={"last_seen_at": iso(), "state": body.result})
    else:
        asset = store.insert("cc_assets", {"id": new_id("ast"), "organization_id": org, "workspace_id": ws["id"], "connection_id": None,
                                        "external_id": ext, "kind": "service", "name": body.service, "provider": "reporter",
                                        "environment": body.environment, "state": body.result, "url": body.url, "last_seen_at": iso(), "created_at": iso()})
        store.insert("inbox_items", {"id": new_id("inb"), "organization_id": org, "workspace_id": ws["id"], "asset_id": asset["id"],
                                     "kind": "new_asset", "status": "open", "reason": "דיווח חיצוני ראשון", "created_at": iso()})
    dup = store.list("activity_events", organization_id=org, workspace_id=ws["id"], external_id=f"report:{body.external_id}")
    if dup:
        return {"ok": True, "duplicate": True, "event_id": dup[0]["id"]}
    pid = next((pa["project_id"] for pa in active_links(store, org, asset_id=asset["id"])), None)
    ev = store.insert("activity_events", {"id": new_id("evt"), "organization_id": org, "workspace_id": ws["id"], "connection_id": None,
                                          "asset_id": asset["id"], "project_id": pid, "external_id": f"report:{body.external_id}",
                                          "kind": body.kind, "result": body.result, "environment": body.environment,
                                          "title": body.title or f"{body.service} {body.kind}", "url": body.url,
                                          "occurred_at": body.occurred_at or iso(), "ingested_at": iso(), "created_at": iso()})
    if body.result == "failure" and body.environment == "production" and pid:
        sync_engine._alert(store, org, ws["id"], "failure", "asset", asset["id"], f"כשל בייצור: {ev['title']}"[:200],
                           occurred_at=ev["occurred_at"])
    return {"ok": True, "duplicate": False, "event_id": ev["id"]}


@router.post("/workspaces/{ws_id}/report-token")
def rotate_report_token(ws_id: str, p: Principal = Depends(current_principal)):
    """Issue a new reporter token. The plaintext is returned once; only its
    hash is stored, so no later read of the workspace can reveal it."""
    require_workspace(p, ws_id, WS_ADMIN)
    import secrets as _s
    token = _s.token_urlsafe(24)
    _store().update("workspaces", ws_id, organization_id=p.organization_id,
                    patch={"report_token_hash": _token_hash(token), "report_token": None})
    audit(p, "cc.workspace.report_token", detail=ws_id)
    return {"workspace_id": ws_id, "report_token": token}


# --- Clients & usage metering (PRD 9.3, extended) -------------------------

class ClientIn(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=160)
    external_ref: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)


class ClientPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    external_ref: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=2000)


@router.get("/clients")
def list_clients(workspace_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    rows = list_in_workspaces(p, "clients", workspace_id)
    projects = list_in_workspaces(p, "cc_projects", workspace_id)
    for c in rows:
        c["projects"] = [{"id": x["id"], "name": x["name"]} for x in projects if x.get("client_id") == c["id"]]
    return sorted(rows, key=lambda c: c["name"])


@router.post("/clients")
def create_client(body: ClientIn, p: Principal = Depends(current_principal)):
    require_workspace(p, body.workspace_id, WS_EDITOR)
    store, org = _store(), p.organization_id
    if any(c["name"].lower() == body.name.strip().lower() for c in store.list("clients", organization_id=org, workspace_id=body.workspace_id)):
        raise HTTPException(status_code=409, detail="client name already exists in this workspace")
    row = {"id": new_id("cli"), "organization_id": org, "workspace_id": body.workspace_id, "name": body.name.strip(),
           "external_ref": body.external_ref, "notes": body.notes, "created_at": iso(), "source": "manual"}
    store.insert("clients", row)
    audit(p, "cc.client.create", detail=f"{row['id']} {row['name']}")
    return row


@router.patch("/clients/{client_id}")
def patch_client(client_id: str, body: ClientPatch, p: Principal = Depends(current_principal)):
    get_in_workspace(p, "clients", client_id, minimum=WS_EDITOR)
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "name" in patch:
        patch["name"] = patch["name"].strip()
    row = _store().update("clients", client_id, organization_id=p.organization_id, patch=patch)
    audit(p, "cc.client.update", detail=f"{client_id} {','.join(patch)}")
    return row


@router.post("/usage")
def report_usage(body: usage_engine.UsageReportIn, x_report_token: Optional[str] = Header(default=None)):
    """Metered usage reported by the integration that made the calls (n8n
    workflow, bot, app), signed with the workspace reporter token. Each entry is
    one metric for one client; `external_id` makes a replay a duplicate."""
    store = _store()
    ws = _workspace_by_token(store, body.workspace_id, x_report_token or "")
    if not ws:
        raise HTTPException(status_code=401, detail="invalid report token")
    org = ws["organization_id"]
    accepted = duplicates = 0
    created: list[str] = []
    for e in body.entries:
        e = usage_engine.normalise(e)
        if e.project_id:
            pr = store.get("cc_projects", e.project_id, organization_id=org)
            if not pr or pr["workspace_id"] != ws["id"]:
                raise HTTPException(status_code=422, detail=f"project {e.project_id} not in workspace")
            if not e.client and not e.client_id and pr.get("client_id"):
                e.client_id = pr["client_id"]      # the project's client by default
        cid = usage_engine.resolve_client(store, org, ws["id"], client_id=e.client_id, name=e.client, created=created)
        _, dup = usage_engine.record(store, org, ws["id"], e, client_id=cid, source="reporter")
        duplicates += dup
        accepted += not dup
    return {"ok": True, "accepted": accepted, "duplicates": duplicates, "clients_created": created}


@router.get("/usage")
def usage_report(workspace_id: Optional[str] = None, client_id: Optional[str] = None, project_id: Optional[str] = None,
                 provider: Optional[str] = None, interface: Optional[str] = None,
                 from_: Optional[str] = Query(default=None, alias="from"), to: Optional[str] = None,
                 limit: int = Query(default=200, le=1000), p: Principal = Depends(current_principal)):
    """Usage for a period (default: the current month) with totals by client,
    provider, interface and project, plus the latest entries."""
    store, org = _store(), p.organization_id
    start, end = usage_engine.window(from_, to)
    rows = usage_engine.filter_entries(list_in_workspaces(p, "usage_entries", workspace_id), start=start, end=end,
                                       client_id=client_id, project_id=project_id, provider=provider, interface=interface)
    clients = {c["id"]: c for c in list_in_workspaces(p, "clients", workspace_id)}
    projects = {x["id"]: x for x in list_in_workspaces(p, "cc_projects", workspace_id)}
    out = usage_engine.summarize(rows, clients, projects)
    for r in rows[:limit]:
        r["client_name"] = clients.get(r.get("client_id") or "", {}).get("name", "")
        r["project_name"] = projects.get(r.get("project_id") or "", {}).get("name", "")
    return {**out, "entries": rows[:limit], "period": {"from": iso(start) if start else None, "to": iso(end) if end else None},
            "providers": list(usage_engine.PROVIDERS), "metrics": list(usage_engine.METRICS)}


# --- Alerts -----------------------------------------------------------------

@router.get("/alerts")
def list_alerts(workspace_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    return sorted(list_in_workspaces(p, "alerts", workspace_id), key=lambda a: str(a.get("created_at")), reverse=True)


class AlertAction(BaseModel):
    action: str   # acknowledge | snooze


@router.post("/alerts/{alert_id}")
def act_alert(alert_id: str, body: AlertAction, p: Principal = Depends(current_principal)):
    get_in_workspace(p, "alerts", alert_id, minimum=WS_EDITOR)
    status = {"acknowledge": "acknowledged", "snooze": "snoozed"}.get(body.action)
    if not status:
        raise HTTPException(status_code=422, detail="unknown action")
    return _store().update("alerts", alert_id, organization_id=p.organization_id, patch={"status": status, "acted_by": p.actor})


# --- Costs (PRD section 9.3) ------------------------------------------------

class CostIn(BaseModel):
    workspace_id: str
    project_id: Optional[str] = None
    provider: str
    kind: str = "reported"            # reported | usage | estimate | allocation | subscription
    amount: float = Field(ge=0, allow_inf_nan=False)
    currency: str = "USD"
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    note: str = ""
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    key_id: Optional[str] = None
    source_ref: str = ""


@router.get("/costs")
def list_costs(workspace_id: Optional[str] = None, project_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    f = {"project_id": project_id} if project_id else {}
    rows = list_in_workspaces(p, "cost_entries", workspace_id, **f)
    total = sum(float(r.get("amount") or 0) for r in rows)
    estimates = sum(float(r.get("amount") or 0) for r in rows if r["kind"] == "estimate")
    tokens = sum(int(r.get("tokens_in") or 0) + int(r.get("tokens_out") or 0) for r in rows)
    return {"entries": rows, "total_usd": round(total, 2), "includes_estimates": estimates > 0,
            "estimates_usd": round(estimates, 2), "tokens": tokens}


@router.post("/costs")
def create_cost(body: CostIn, p: Principal = Depends(current_principal)):
    require_workspace(p, body.workspace_id, WS_EDITOR)
    if body.project_id:
        pr = get_in_workspace(p, "cc_projects", body.project_id)
        if pr["workspace_id"] != body.workspace_id:
            raise HTTPException(status_code=422, detail="project not in workspace")
    row = {"id": new_id("cost"), "organization_id": p.organization_id, "created_at": iso(), "created_by": p.actor, **body.model_dump()}
    _store().insert("cost_entries", row)
    audit(p, "cc.cost.create", detail=f"{row['id']} {body.provider} {body.amount}")
    return row


# --- Provider keys (PRD section 9.2) ---------------------------------------

class KeyIn(BaseModel):
    workspace_id: str
    name: str
    provider: str = "anthropic"
    account_label: str = ""
    secret: str = Field(min_length=8)
    scope: str = "model_calls"


@router.get("/keys")
def list_keys(workspace_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    rows = [public(r) for r in list_in_workspaces(p, "provider_keys", workspace_id)]
    for r in rows:
        r["used_by_projects"] = [x["name"] for x in store.list("cc_projects", organization_id=org, workspace_id=r["workspace_id"]) if x.get("default_key_id") == r["id"]]
        r["used_by_agents"] = [a["name"] for a in store.list("cc_agents", organization_id=org, workspace_id=r["workspace_id"]) if a.get("key_id") == r["id"]]
    return rows


@router.post("/keys")
def create_key(body: KeyIn, p: Principal = Depends(current_principal)):
    require_workspace(p, body.workspace_id, WS_ADMIN)
    try:
        enc = encrypt(body.secret)
    except SecretsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    row = {"id": new_id("key"), "organization_id": p.organization_id, "workspace_id": body.workspace_id, "name": body.name,
           "provider": body.provider, "account_label": body.account_label, "masked": mask(body.secret), "scope": body.scope,
           "created_at": iso(), "secret_enc": enc, "version": 1}
    _store().insert("provider_keys", row)
    audit(p, "cc.key.create", detail=f"{row['id']} {body.provider}")
    return public(row)


class KeyRotate(BaseModel):
    secret: str = Field(min_length=8)


@router.post("/keys/{key_id}/rotate")
def rotate_key(key_id: str, body: KeyRotate, p: Principal = Depends(current_principal)):
    k = get_in_workspace(p, "provider_keys", key_id, minimum=WS_ADMIN)
    store, org = _store(), p.organization_id
    affected = {"projects": [x["name"] for x in store.list("cc_projects", organization_id=org, workspace_id=k["workspace_id"]) if x.get("default_key_id") == key_id],
                "agents": [a["name"] for a in store.list("cc_agents", organization_id=org, workspace_id=k["workspace_id"]) if a.get("key_id") == key_id]}
    try:
        enc = encrypt(body.secret)
    except SecretsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    row = store.update("provider_keys", key_id, organization_id=org, patch={"secret_enc": enc, "masked": mask(body.secret), "version": int(k.get("version", 1)) + 1})
    audit(p, "cc.key.rotate", detail=f"{key_id} v{row['version']}")
    return {**public(row), "affected": affected}


# --- Agents (PRD section 9.4) ------------------------------------------------

class AgentIn(BaseModel):
    workspace_id: str
    project_id: Optional[str] = None
    name: str = Field(min_length=1, max_length=80)
    instructions: str = Field(default="", max_length=4000)
    owner: str = ""
    provider: str = "anthropic"
    model: str = "claude-opus-5-5"
    key_id: Optional[str] = None
    tools: list[str] = Field(default_factory=lambda: ["catalog.read"])
    allowed_projects: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=lambda: {"max_steps": 10, "max_seconds": 120, "max_tokens": 20000, "max_cost_usd": 1.0})
    approval_rule: str = "read_only"
    enabled: bool = True


@router.get("/agents")
def list_agents(workspace_id: Optional[str] = None, project_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    rows = list_in_workspaces(p, "cc_agents", workspace_id)
    if project_id:
        rows = [a for a in rows if a.get("project_id") in (None, "", project_id)]
    return rows


@router.post("/agents")
def create_agent(body: AgentIn, p: Principal = Depends(current_principal)):
    require_workspace(p, body.workspace_id, WS_EDITOR)
    if body.project_id:
        pr = get_in_workspace(p, "cc_projects", body.project_id)
        if pr["workspace_id"] != body.workspace_id:
            raise HTTPException(status_code=422, detail="project not in workspace")
    if body.key_id:
        k = _store().get("provider_keys", body.key_id, organization_id=p.organization_id)
        if not k or k["workspace_id"] != body.workspace_id:
            raise HTTPException(status_code=422, detail="key must belong to the workspace")   # PRD 9.5
    row = {"id": new_id("agt"), "organization_id": p.organization_id, "version": 1, "created_at": iso(),
           "owner": body.owner or (p.display_name or p.email), **body.model_dump(exclude={"owner"})}
    _store().insert("cc_agents", row)
    audit(p, "cc.agent.create", detail=row["id"])
    return row


@router.patch("/agents/{agent_id}")
def update_agent(agent_id: str, body: AgentIn, p: Principal = Depends(current_principal)):
    a = get_in_workspace(p, "cc_agents", agent_id, minimum=WS_EDITOR)
    if body.workspace_id != a["workspace_id"]:
        raise HTTPException(status_code=422, detail="workspace change requires the transfer wizard")
    # Project references must stay inside the agent's workspace (same rule as create).
    for pid in [body.project_id] + list(body.allowed_projects):
        if pid:
            pr = _store().get("cc_projects", pid, organization_id=p.organization_id)
            if not pr or pr["workspace_id"] != a["workspace_id"]:
                raise HTTPException(status_code=422, detail="project not in workspace")
    if body.key_id:
        k = _store().get("provider_keys", body.key_id, organization_id=p.organization_id)
        if not k or k["workspace_id"] != a["workspace_id"]:
            raise HTTPException(status_code=422, detail="key must belong to the workspace")
    patch = {**body.model_dump(), "version": int(a.get("version", 1)) + 1}
    if not body.owner:
        patch["owner"] = a.get("owner", "")   # an edit never blanks the owner
    row = _store().update("cc_agents", agent_id, organization_id=p.organization_id, patch=patch)
    audit(p, "cc.agent.update", detail=f"{agent_id} v{row['version']}")
    return row


class RunIn(BaseModel):
    project_id: str
    session_id: Optional[str] = None
    idempotency_key: Optional[str] = None


@router.post("/agents/{agent_id}/runs")
def run_agent(agent_id: str, body: RunIn, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    a = get_in_workspace(p, "cc_agents", agent_id, minimum=WS_EDITOR)
    pr = get_in_workspace(p, "cc_projects", body.project_id, minimum=WS_EDITOR)
    if pr["workspace_id"] != a["workspace_id"]:
        raise HTTPException(status_code=403, detail="agent cannot run outside its workspace")
    if not a.get("enabled", True):
        raise HTTPException(status_code=409, detail="agent is disabled")
    if a.get("project_id") and a["project_id"] != pr["id"]:
        raise HTTPException(status_code=403, detail="dedicated agent is bound to another project")
    if not a.get("project_id") and a.get("allowed_projects") and pr["id"] not in a["allowed_projects"]:
        raise HTTPException(status_code=403, detail="project not allowed for this agent")
    if body.session_id:
        s = get_in_workspace(p, "work_sessions", body.session_id)
        if s["project_id"] != pr["id"]:
            raise HTTPException(status_code=422, detail="session belongs to another project")
    # Idempotency (PRD 9.4.2): a double click never creates a second run.
    def _existing_run() -> Optional[Row]:
        for r in store.list("agent_runs", organization_id=org, workspace_id=a["workspace_id"], agent_id=agent_id):
            if r.get("idempotency_key") == body.idempotency_key:
                return r
        return None

    if body.idempotency_key and (prev := _existing_run()):
        return prev
    # Budget check including concurrent runs (PRD 9.4.2). Limits and amounts are
    # clamped so a negative or NaN value can never make the check pass.
    try:
        limit = max(0.0, float((a.get("limits") or {}).get("max_cost_usd") or 0))
    except (TypeError, ValueError):
        limit = 0.0
    if limit != limit:  # NaN
        limit = 0.0
    budget = float(pr.get("budget_usd") or 0)
    if budget > 0:
        spent = sum(max(0.0, float(c.get("amount") or 0)) for c in store.list("cost_entries", organization_id=org, workspace_id=pr["workspace_id"], project_id=pr["id"])
                    if _month(c) == now().strftime("%Y-%m"))
        running = store.list("agent_runs", organization_id=org, workspace_id=a["workspace_id"], project_id=pr["id"], status="running")
        if spent + limit * (len(running) + 1) > budget:
            raise HTTPException(status_code=409, detail="project budget would be exceeded")
    run = {"id": new_id("arun"), "organization_id": org, "workspace_id": a["workspace_id"], "agent_id": agent_id,
           "project_id": pr["id"], "session_id": body.session_id, "status": "queued", "created_at": iso(),
           "idempotency_key": body.idempotency_key, "requested_by": p.actor, "agent_name": a["name"]}
    try:
        store.insert("agent_runs", run)
    except Exception as exc:
        # Concurrent submission with the same key: the partial unique index
        # (migration 0005) rejects the second insert; return the first run.
        if body.idempotency_key and "unique" in str(exc).lower() and (prev := _existing_run()):
            return prev
        raise
    audit(p, "cc.agent.run", detail=f"{run['id']} agent={agent_id} project={pr['id']}", run_id=run["id"])
    final = agent_engine.execute_run(store, org, run, a, pr, actor=p.actor)
    audit(p, "cc.agent.run.finish", decision=final["status"], detail=run["id"], run_id=run["id"])
    return final


@router.get("/runs")
def list_runs(workspace_id: Optional[str] = None, project_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    f = {"project_id": project_id} if project_id else {}
    return sorted(list_in_workspaces(p, "agent_runs", workspace_id, **f), key=lambda r: str(r.get("created_at")), reverse=True)


@router.get("/runs/{run_id}")
def get_run(run_id: str, p: Principal = Depends(current_principal)):
    store, org = _store(), p.organization_id
    r = get_in_workspace(p, "agent_runs", run_id)
    return {"run": r, "agent": store.get("cc_agents", r["agent_id"], organization_id=org),
            "project": store.get("cc_projects", r["project_id"], organization_id=org)}


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, p: Principal = Depends(current_principal)):
    r = get_in_workspace(p, "agent_runs", run_id, minimum=WS_EDITOR)
    if r["status"] in ("completed", "failed", "cancelled"):
        return r
    row = _store().update("agent_runs", run_id, organization_id=p.organization_id, patch={"status": "cancelled", "finished_at": iso()})
    audit(p, "cc.agent.run.cancel", detail=run_id, run_id=run_id)
    return row


# --- Link to the PT module --------------------------------------------------

class LinkPtIn(BaseModel):
    pt_project_id: str


@router.post("/projects/{project_id}/pt")
def link_pt_project(project_id: str, body: LinkPtIn, p: Principal = Depends(current_principal)):
    """Attach a PT survey project to a control-center project. Writing to the PT
    project follows the PT rules (survey manager / org admin), and an existing
    link is only moved by someone who may edit the project it points to."""
    get_in_workspace(p, "cc_projects", project_id, minimum=WS_EDITOR)
    if p.role not in (Role.ORG_ADMIN, Role.SURVEY_MANAGER):
        raise HTTPException(status_code=403, detail="survey manager or organisation admin required")
    ptp = _store().get("projects", body.pt_project_id, organization_id=p.organization_id)
    if not ptp:
        raise HTTPException(status_code=404, detail="pt project not found")
    prev = ptp.get("cc_project_id")
    if prev and prev != project_id:
        try:
            get_in_workspace(p, "cc_projects", prev, minimum=WS_EDITOR)
        except HTTPException:
            raise HTTPException(status_code=409, detail="pt project is linked to a project you cannot edit")
    row = _store().update("projects", body.pt_project_id, organization_id=p.organization_id, patch={"cc_project_id": project_id})
    audit(p, "cc.project.link_pt", detail=f"{project_id} <- {body.pt_project_id}" + (f" (was {prev})" if prev else ""))
    return row
