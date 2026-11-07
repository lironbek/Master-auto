"""HTTP API — PRD section 17, extended for the UI (section 14).

Every request is scoped by the organisation of the authenticated principal.
An object id in a path never replaces the ownership check (acceptance
criterion 2). Persistence goes through ``pt_agent.storage``.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..evidence import EvidenceVault, RedactionError, assert_clean, redact
from ..findings.finding import _TRANSITIONS
from ..models import (
    AuditEvent,
    Authorization,
    Confidence,
    Evidence,
    EvidenceKind,
    Finding,
    FindingStatus,
    OperatingMode,
    Project,
    ReportVersion,
    Role,
    RunBudget,
    RunStatus,
    ScanRun,
    ScopeVersion,
    ScopeVersionStatus,
    Severity,
    TargetSpec,
)
from ..reports import render_json, render_markdown
from ..storage import backend_name, get_store, postgres_dsn
from .auth import Principal, current_principal, require_role
from .auth import router as auth_router

_migration_state: dict = {"ran": False, "applied": [], "error": ""}


def _auto_migrate() -> None:
    """Apply pending SQL migrations on cold start when a Postgres DSN is set."""
    dsn = postgres_dsn()
    if not dsn or os.environ.get("PT_AUTO_MIGRATE", "1") == "0":
        return
    try:
        from ..db.migrate import migrate

        _migration_state["applied"] = migrate(dsn)
        _migration_state["ran"] = True
    except Exception as exc:  # surface in /healthz rather than crash the app
        _migration_state["error"] = f"{type(exc).__name__}: {exc}"[:300]


@asynccontextmanager
async def _lifespan(_: FastAPI):
    _auto_migrate()
    yield


app = FastAPI(title="PT Agent — governance API", version="0.2.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("PT_CORS_ORIGINS", "http://localhost:5173").split(",") if o],
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth_router)

# The vault is the redaction gate for evidence submitted through the API.
_vault = EvidenceVault()

MANAGER_ROLES = (Role.ORG_ADMIN, Role.SURVEY_MANAGER)
TESTER_ROLES = (Role.ORG_ADMIN, Role.SURVEY_MANAGER, Role.PT_TESTER)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dump(model: BaseModel) -> dict:
    return model.model_dump(mode="json")


def _get_or_404(table: str, row_id: str, org: str) -> dict:
    row = get_store().get(table, row_id, organization_id=org)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return row


def _audit(org: str, actor: str, action: str, *, run_id: str | None = None,
           decision: str = "", detail: str = "") -> None:
    ev = AuditEvent(organization_id=org, run_id=run_id, actor=actor,
                    action=action, decision=decision, detail=detail)
    get_store().insert("audit_events", _dump(ev))


def _org_key() -> bytes | None:
    return os.environ.get("PT_ORG_HMAC_KEY", "").encode() or None


def _clean_text(value: str, *, field: str) -> str:
    """Free text written by a person goes through the same redaction gate as
    evidence: secrets are masked, and if masking cannot be completed the
    request is refused (PRD section 10, fail closed)."""
    try:
        out = redact(value or "", org_key=_org_key()).text
        assert_clean(out)
        return out
    except RedactionError as exc:
        raise HTTPException(status_code=422, detail=f"{field}: redaction failed; not stored ({exc})")


def _within_run_window(scope: dict) -> bool:
    start, end = scope.get("run_window_start"), scope.get("run_window_end")
    t = _now()

    def _dt(v):
        if not v:
            return None
        d = v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

    s, e = _dt(start), _dt(end)
    return (s is None or s <= t) and (e is None or t <= e)


# --- Projects ---------------------------------------------------------------

class CreateProject(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""


@app.post("/projects")
def create_project(body: CreateProject, p: Principal = Depends(require_role(*MANAGER_ROLES))):
    project = Project(organization_id=p.organization_id, name=body.name, description=body.description)
    get_store().insert("projects", _dump(project))
    _audit(p.organization_id, p.actor, "project.create", detail=project.id)
    return project


@app.get("/projects")
def list_projects(p: Principal = Depends(current_principal)):
    return get_store().list("projects", organization_id=p.organization_id)


@app.get("/projects/{project_id}")
def get_project(project_id: str, p: Principal = Depends(current_principal)):
    org = p.organization_id
    project = _get_or_404("projects", project_id, org)
    store = get_store()
    return {
        "project": project,
        "authorizations": store.list("authorizations", organization_id=org, project_id=project_id),
        "scope_versions": store.list("scope_versions", organization_id=org, project_id=project_id),
        "runs": store.list("scan_runs", organization_id=org, project_id=project_id),
        "findings": store.list("findings", organization_id=org, project_id=project_id),
    }


# --- Authorizations (PRD section 4) ---------------------------------------

class CreateAuthorization(BaseModel):
    approver_name: str
    approver_authority: str
    valid_from: datetime
    valid_until: datetime
    control_verified: bool = False
    document_reference: str = ""


@app.post("/projects/{project_id}/authorizations")
def create_authorization(project_id: str, body: CreateAuthorization,
                         p: Principal = Depends(require_role(*MANAGER_ROLES))):
    org = p.organization_id
    _get_or_404("projects", project_id, org)
    if body.valid_until <= body.valid_from:
        raise HTTPException(status_code=422, detail="valid_until must be after valid_from")
    auth = Authorization(organization_id=org, project_id=project_id, **body.model_dump())
    get_store().insert("authorizations", _dump(auth))
    _audit(org, p.actor, "authorization.create", detail=auth.id)
    return auth


# --- Scope versions ---------------------------------------------------------

class CreateScope(BaseModel):
    authorization_id: str
    environment: str = "test"
    targets: list[TargetSpec]
    allowed_modules: list[str] = Field(default_factory=lambda: ["passive.security_headers", "passive.cookie_flags"])
    allowed_modes: list[OperatingMode] = Field(default_factory=lambda: [OperatingMode.PASSIVE])
    budget: RunBudget = Field(default_factory=RunBudget)
    stop_conditions: list[str] = Field(default_factory=list)
    run_window_start: Optional[datetime] = None
    run_window_end: Optional[datetime] = None


@app.post("/projects/{project_id}/scope-versions")
def create_scope_version(project_id: str, body: CreateScope,
                         p: Principal = Depends(require_role(*MANAGER_ROLES))):
    org = p.organization_id
    _get_or_404("projects", project_id, org)
    _get_or_404("authorizations", body.authorization_id, org)
    if not body.targets:
        raise HTTPException(status_code=422, detail="at least one target is required")
    existing = get_store().list("scope_versions", organization_id=org, project_id=project_id)
    scope = ScopeVersion(organization_id=org, project_id=project_id, version=len(existing) + 1,
                         status=ScopeVersionStatus.DRAFT, **body.model_dump())
    get_store().insert("scope_versions", _dump(scope))
    _audit(org, p.actor, "scope.create", detail=f"{scope.id} v{scope.version}")
    return scope


@app.get("/scope-versions/{scope_id}")
def get_scope_version(scope_id: str, p: Principal = Depends(current_principal)):
    return _get_or_404("scope_versions", scope_id, p.organization_id)


@app.post("/scope-versions/{scope_id}/approve")
def approve_scope(scope_id: str, p: Principal = Depends(require_role(*MANAGER_ROLES))):
    org = p.organization_id
    scope = _get_or_404("scope_versions", scope_id, org)
    if scope["status"] == ScopeVersionStatus.APPROVED.value:
        return scope
    # Approving a new version supersedes earlier approved versions (section 4).
    for other in get_store().list("scope_versions", organization_id=org, project_id=scope["project_id"]):
        if other["id"] != scope_id and other["status"] == ScopeVersionStatus.APPROVED.value:
            get_store().update("scope_versions", other["id"], organization_id=org,
                               patch={"status": ScopeVersionStatus.SUPERSEDED.value})
    row = get_store().update("scope_versions", scope_id, organization_id=org, patch={
        "status": ScopeVersionStatus.APPROVED.value, "approved_by": p.user_id,
        "approved_at": _now().isoformat(),
    })
    _audit(org, p.actor, "scope.approve", detail=scope_id)
    return row


# --- Runs -------------------------------------------------------------------

class StartRun(BaseModel):
    scope_version_id: str
    mode: OperatingMode = OperatingMode.PASSIVE


def _load_run_context(run_row: dict, org: str) -> tuple[ScanRun, ScopeVersion, Authorization]:
    scope_row = _get_or_404("scope_versions", run_row["scope_version_id"], org)
    auth_row = _get_or_404("authorizations", scope_row["authorization_id"], org)
    return ScanRun(**run_row), ScopeVersion(**scope_row), Authorization(**auth_row)


@app.post("/runs")
def create_run(body: StartRun, p: Principal = Depends(require_role(*TESTER_ROLES))):
    org = p.organization_id
    scope = _get_or_404("scope_versions", body.scope_version_id, org)
    if scope.get("status") != ScopeVersionStatus.APPROVED.value:
        raise HTTPException(status_code=409, detail="scope version not approved")
    if body.mode.value not in (scope.get("allowed_modes") or [OperatingMode.PASSIVE.value]):
        raise HTTPException(status_code=409, detail="mode not permitted by scope")
    auth = Authorization(**_get_or_404("authorizations", scope["authorization_id"], org))
    if not auth.is_valid_at():
        raise HTTPException(status_code=409, detail="authorization not valid now")
    if not _within_run_window(scope):
        raise HTTPException(status_code=409, detail="outside the approved run window")
    if body.mode is not OperatingMode.PASSIVE:
        raise HTTPException(status_code=409, detail="only passive runs are enabled in this build")
    run = ScanRun(organization_id=org, project_id=scope["project_id"],
                  scope_version_id=scope["id"], mode=body.mode)
    get_store().insert("scan_runs", _dump(run))
    _audit(org, p.actor, "run.create", run_id=run.id)
    return run


@app.post("/runs/{run_id}/start")
def start_run(run_id: str, p: Principal = Depends(require_role(*TESTER_ROLES))):
    """Execute the run now (passive modules, bounded, governed)."""
    org = p.organization_id
    row = _get_or_404("scan_runs", run_id, org)
    if row["status"] not in (RunStatus.CREATED.value,):
        raise HTTPException(status_code=409, detail=f"run is {row['status']}")
    run, scope, auth = _load_run_context(row, org)
    if scope.status is not ScopeVersionStatus.APPROVED:
        raise HTTPException(status_code=409, detail="scope version no longer approved")
    if not auth.is_valid_at():
        raise HTTPException(status_code=409, detail="authorization not valid now")
    if not _within_run_window(scope.model_dump()):
        raise HTTPException(status_code=409, detail="outside the approved run window")
    get_store().update("scan_runs", run_id, organization_id=org, patch={
        "status": RunStatus.RUNNING.value, "started_at": _now().isoformat()})
    run.status = RunStatus.RUNNING
    from ..agent.runner import execute_run

    summary = execute_run(run, scope, auth, get_store(), org_key=_org_key(), actor=p.actor)
    return {"run_id": run_id, "summary": summary,
            "run": get_store().get("scan_runs", run_id, organization_id=org)}


@app.get("/runs")
def list_runs(project_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    f = {"project_id": project_id} if project_id else {}
    return get_store().list("scan_runs", organization_id=p.organization_id, **f)


@app.get("/runs/{run_id}")
def get_run(run_id: str, p: Principal = Depends(current_principal)):
    org = p.organization_id
    run = _get_or_404("scan_runs", run_id, org)
    store = get_store()
    return {
        "run": run,
        "scope_version": store.get("scope_versions", run["scope_version_id"], organization_id=org),
        "events": store.list("audit_events", organization_id=org, run_id=run_id),
        "actions": store.list("actions", organization_id=org, run_id=run_id),
        "findings": store.list("findings", organization_id=org, run_id=run_id),
    }


@app.post("/runs/{run_id}/stop")
def stop_run(run_id: str, p: Principal = Depends(require_role(*TESTER_ROLES))):
    """Stop is independent of model availability (PRD section 18)."""
    org = p.organization_id
    _get_or_404("scan_runs", run_id, org)
    row = get_store().update("scan_runs", run_id, organization_id=org, patch={
        "status": RunStatus.STOPPED.value, "stopped_at": _now().isoformat(),
        "stop_reason": "operator stop"})
    _audit(org, p.actor, "run.stop", run_id=run_id)
    return row


@app.get("/runs/{run_id}/events")
def run_events(run_id: str, p: Principal = Depends(current_principal)):
    org = p.organization_id
    run = _get_or_404("scan_runs", run_id, org)
    events = get_store().list("audit_events", organization_id=org, run_id=run_id)
    return {"run_id": run["id"], "status": run["status"], "events": events}


# --- Findings & evidence ----------------------------------------------------

@app.get("/findings")
def list_findings(project_id: Optional[str] = None, run_id: Optional[str] = None,
                  p: Principal = Depends(current_principal)):
    f = {}
    if project_id:
        f["project_id"] = project_id
    if run_id:
        f["run_id"] = run_id
    return get_store().list("findings", organization_id=p.organization_id, **f)


class CreateFinding(BaseModel):
    """What a tester may submit. Identity, project, organisation and status are
    derived server-side; free text passes the redaction gate."""
    run_id: str
    title: str = Field(min_length=1, max_length=200)
    asset_path: str = ""
    category: str = ""
    severity: Severity = Severity.MEDIUM
    confidence: Confidence = Confidence.SUSPECTED
    preconditions: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    expected_result: str = ""
    actual_result: str = ""
    proven_impact: str = ""
    inferred_impact: str = ""
    reproduction: str = ""
    remediation: str = ""
    limitations: str = ""
    owner: str = ""


_FINDING_TEXT = ("title", "asset_path", "preconditions", "expected_result", "actual_result",
                 "proven_impact", "inferred_impact", "reproduction", "remediation", "limitations")


@app.post("/findings")
def create_finding(body: CreateFinding, p: Principal = Depends(require_role(*TESTER_ROLES))):
    org = p.organization_id
    run = _get_or_404("scan_runs", body.run_id, org)
    store = get_store()
    for eid in body.evidence_ids:
        if store.get("evidence", eid, organization_id=org) is None:
            raise HTTPException(status_code=422, detail=f"evidence {eid} not found")
    data = body.model_dump()
    for k in _FINDING_TEXT:
        data[k] = _clean_text(data[k], field=k)
    finding = Finding(organization_id=org, project_id=run["project_id"], status=FindingStatus.NEW, **data)
    store.insert("findings", _dump(finding))
    _audit(org, p.actor, "finding.create", run_id=finding.run_id, detail=finding.id)
    return finding


@app.get("/findings/{finding_id}")
def get_finding(finding_id: str, p: Principal = Depends(current_principal)):
    org = p.organization_id
    finding = _get_or_404("findings", finding_id, org)
    store = get_store()
    evidence = [e for e in (store.get("evidence", eid, organization_id=org) for eid in finding.get("evidence_ids", [])) if e]
    for e in evidence:
        store.insert("evidence_access_log", {"organization_id": org, "evidence_id": e["id"],
                                             "actor": p.actor, "action": "view", "at": _now().isoformat()})
    return {"finding": finding, "evidence": evidence}


class FindingStatusChange(BaseModel):
    status: FindingStatus
    note: str = ""


@app.post("/findings/{finding_id}/status")
def change_finding_status(finding_id: str, body: FindingStatusChange,
                          p: Principal = Depends(require_role(*TESTER_ROLES, Role.DEVELOPER))):
    org = p.organization_id
    finding = _get_or_404("findings", finding_id, org)
    current = FindingStatus(finding["status"])
    if body.status not in _TRANSITIONS.get(current, set()):
        raise HTTPException(status_code=409, detail=f"{current.value} -> {body.status.value} not allowed")
    note = _clean_text(body.note, field="note")   # the audit log is append-only: never a raw secret
    row = get_store().update("findings", finding_id, organization_id=org, patch={"status": body.status.value})
    _audit(org, p.actor, "finding.status", run_id=finding.get("run_id"),
           decision=body.status.value, detail=f"{finding_id} {note}"[:300])
    return row


class StoreEvidence(BaseModel):
    project_id: str
    kind: EvidenceKind
    raw_snippet: str
    finding_id: Optional[str] = None


@app.post("/evidence")
def store_evidence(body: StoreEvidence, p: Principal = Depends(require_role(*TESTER_ROLES))):
    """Redaction runs in memory before anything is persisted (PRD section 10)."""
    org = p.organization_id
    _get_or_404("projects", body.project_id, org)
    try:
        ev = _vault.store(organization_id=org, project_id=body.project_id, kind=body.kind,
                          raw_snippet=body.raw_snippet, org_key=_org_key(), actor=p.actor,
                          finding_id=body.finding_id)
    except RedactionError as exc:
        _audit(org, p.actor, "evidence.store_refused", detail=str(exc))
        raise HTTPException(status_code=422, detail="redaction failed; evidence not stored")
    get_store().insert("evidence", _dump(ev))
    get_store().insert("evidence_access_log", {"organization_id": org, "evidence_id": ev.id,
                                               "actor": p.actor, "action": "store", "at": _now().isoformat()})
    return ev


@app.get("/evidence")
def list_evidence(project_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    f = {"project_id": project_id} if project_id else {}
    return get_store().list("evidence", organization_id=p.organization_id, **f)


@app.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str, p: Principal = Depends(current_principal)):
    org = p.organization_id
    row = _get_or_404("evidence", evidence_id, org)
    get_store().insert("evidence_access_log", {"organization_id": org, "evidence_id": evidence_id,
                                               "actor": p.actor, "action": "view", "at": _now().isoformat()})
    log = get_store().list("evidence_access_log", organization_id=org, evidence_id=evidence_id)
    return {"evidence": row, "access_log": log}


# --- Reports ----------------------------------------------------------------

class CreateReport(BaseModel):
    run_id: str
    fmt: str = "markdown"


@app.post("/reports")
def create_report(body: CreateReport, p: Principal = Depends(require_role(*TESTER_ROLES))):
    org = p.organization_id
    run = ScanRun(**_get_or_404("scan_runs", body.run_id, org))
    store = get_store()
    findings = [Finding(**f) for f in store.list("findings", organization_id=org, run_id=run.id)]
    view = EvidenceVault()
    for f in findings:
        for eid in f.evidence_ids:
            row = store.get("evidence", eid, organization_id=org)
            if row:
                view._items[eid] = Evidence(**row)
    try:
        content = render_json(run, findings) if body.fmt == "json" else render_markdown(run, findings, view, organization_id=org)
    except RedactionError as exc:
        _audit(org, p.actor, "report.refused", run_id=run.id, decision="blocked", detail=str(exc)[:300])
        raise HTTPException(status_code=422, detail="report refused: unredacted secret in findings or evidence")
    rv = ReportVersion(organization_id=org, project_id=run.project_id, run_id=run.id,
                       finding_ids=[f.id for f in findings],
                       evidence_ids=sorted({e for f in findings for e in f.evidence_ids}))
    row = _dump(rv)
    row.update({"format": body.fmt, "content": content, "created_by": p.actor})
    store.insert("report_versions", row)
    _audit(org, p.actor, "report.create", run_id=run.id, detail=f"{rv.id} {body.fmt}")
    return row


@app.get("/reports")
def list_reports(project_id: Optional[str] = None, p: Principal = Depends(current_principal)):
    f = {"project_id": project_id} if project_id else {}
    rows = get_store().list("report_versions", organization_id=p.organization_id, **f)
    return [{k: v for k, v in r.items() if k != "content"} for r in rows]


@app.get("/reports/{report_id}")
def get_report(report_id: str, p: Principal = Depends(current_principal)):
    return _get_or_404("report_versions", report_id, p.organization_id)


# --- Audit & dashboard ------------------------------------------------------

@app.get("/audit")
def list_audit(limit: int = Query(default=200, le=1000), p: Principal = Depends(current_principal)):
    rows = get_store().list("audit_events", organization_id=p.organization_id)
    return rows[-limit:][::-1]


@app.get("/dashboard")
def dashboard(p: Principal = Depends(current_principal)):
    org = p.organization_id
    store = get_store()
    projects = store.list("projects", organization_id=org)
    runs = store.list("scan_runs", organization_id=org)
    findings = store.list("findings", organization_id=org)
    audit = store.list("audit_events", organization_id=org)
    by_status: dict[str, int] = {}
    for r in runs:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    by_sev: dict[str, int] = {}
    open_count = 0
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        if f["status"] not in ("fixed", "accepted_risk", "false_positive"):
            open_count += 1
    return {
        "projects": len(projects),
        "runs": {"total": len(runs), "by_status": by_status},
        "findings": {"total": len(findings), "open": open_count, "by_severity": by_sev},
        "recent_runs": runs[-5:][::-1],
        "recent_findings": findings[-5:][::-1],
        "recent_events": audit[-10:][::-1],
        "storage": backend_name(),
    }


@app.get("/healthz")
def healthz():
    out = {"status": "ok", "storage": backend_name(), "version": app.version}
    if backend_name() == "postgres":
        out["migrations"] = _migration_state
        if _migration_state["error"]:
            out["status"] = "degraded"
    return out
