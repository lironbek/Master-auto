"""Run executor — wires the governance loop to a real, bounded fetch.

Runs the *passive* reference modules against each approved target. The fetch
is the only network path: every URL (and any redirect) is validated by the
``EgressValidator`` first, responses are capped in size and time, and the
result is redacted before storage. Audit events, evidence and findings are
persisted through the store so the UI can show the run as it happened.
"""

from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from ..evidence import EvidenceVault, RedactionError
from ..models import (
    Action,
    AuditEvent,
    Authorization,
    Confidence,
    Evidence,
    EvidenceKind,
    Finding,
    OperatingMode,
    RiskLevel,
    RunStatus,
    ScanRun,
    ScopeVersion,
    Severity,
)
from ..orchestrator import BudgetState, Orchestrator
from ..policy import ActionFacts, PolicyEngine
from ..scope import EgressValidator
from .gateway import CookieFlagsModule, SecurityHeadersModule, ToolGateway
from .loop import AgentLoop

MAX_BODY_BYTES = 200_000
FETCH_TIMEOUT = 10.0
PASSIVE_MODULES = {
    "passive.security_headers": SecurityHeadersModule,
    "passive.cookie_flags": CookieFlagsModule,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve(host: str) -> list[str]:
    try:
        return sorted({ai[4][0] for ai in socket.getaddrinfo(host, None)})
    except socket.gaierror:
        return []


def lab_allow_internal() -> bool:
    """Only for an isolated lab (PRD section 22); never set in production."""
    return os.environ.get("PT_ALLOW_INTERNAL_TARGETS") == "1"


def make_fetch(validator: EgressValidator, budget: BudgetState):
    """Return a bounded fetch(url) -> text that re-validates redirects and the
    addresses the hostname resolves to (PRD section 9)."""

    def guard(url: str) -> None:
        d = validator.check(url)
        if not d.allowed:
            raise PermissionError(f"egress blocked: {d.reason}")
        assert d.target is not None
        r = validator.check_resolved(d.target.host, _resolve(d.target.host))
        if not r.allowed:
            raise PermissionError(f"egress blocked: {r.reason}")

    def fetch(url: str) -> str:
        guard(url)
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=False,
                          headers={"User-Agent": "pt-agent-passive/0.1"}) as client:
            r = client.get(url)
            hops = 0
            while r.is_redirect and hops < 3:
                loc = r.headers.get("location", "")
                target = str(httpx.URL(url).join(loc))
                try:
                    guard(target)
                except PermissionError as exc:
                    raise PermissionError(f"redirect blocked: {exc} -> {target}") from exc
                url = target
                r = client.get(url)
                hops += 1
                budget.charge_request()
        body = r.content[:MAX_BODY_BYTES].decode(r.encoding or "utf-8", errors="replace")
        head = "\n".join(f"{k}: {v}" for k, v in r.headers.multi_items())
        return f"HTTP/1.1 {r.status_code} {r.reason_phrase}\n{head}\n\n{body}"

    return fetch


def _finding_from_observations(run: ScanRun, module: str, target: str,
                               observations: list[str], evidence_id: Optional[str]) -> Optional[Finding]:
    issues = [o for o in observations if o.startswith("missing header") or "without" in o]
    if not issues:
        return None
    if module == "passive.security_headers":
        title, cat, sev = "Missing HTTP security headers", "config", Severity.LOW
        remediation = "Add the missing headers (HSTS, CSP, X-Content-Type-Options, X-Frame-Options)."
    else:
        title, cat, sev = "Cookie without Secure/HttpOnly flags", "config", Severity.MEDIUM
        remediation = "Set Secure and HttpOnly (and SameSite) on session cookies."
    return Finding(
        organization_id=run.organization_id, project_id=run.project_id, run_id=run.id,
        title=title, asset_path=target, category=cat, severity=sev,
        confidence=Confidence.VERIFIED, evidence_ids=[evidence_id] if evidence_id else [],
        expected_result="hardening headers / cookie flags present",
        actual_result="; ".join(sorted(set(issues))),
        proven_impact="configuration gap observed in a normal response",
        inferred_impact="depends on application context; not exploited",
        reproduction=f"GET {target} and inspect response headers",
        remediation=remediation,
        limitations="passive observation of one response only",
    )


def execute_run(run: ScanRun, scope: ScopeVersion, authorization: Authorization,
                store: Any, *, org_key: bytes | None, actor: str) -> dict:
    """Execute a passive run synchronously and persist everything. Returns a summary."""

    def audit(action: str, decision: str = "", detail: str = "") -> None:
        store.insert("audit_events", AuditEvent(
            organization_id=run.organization_id, run_id=run.id, actor=actor,
            action=action, decision=decision, policy_version=scope.policy_version, detail=detail,
        ).model_dump(mode="json"))

    orch = Orchestrator()
    validator = EgressValidator(scope, allow_internal=lab_allow_internal())
    budget = BudgetState(budget=scope.budget)
    gateway = ToolGateway(validator)
    modules = [m for m in scope.allowed_modules if m in PASSIVE_MODULES] or list(PASSIVE_MODULES)
    for name in modules:
        gateway.register(PASSIVE_MODULES[name]())
    vault = EvidenceVault()

    def target_url(tspec) -> str:
        port = "" if tspec.ports and tspec.ports[0] in (80, 443) else f":{tspec.ports[0]}"
        path = (tspec.allowed_paths or ["/"])[0]
        return f"{tspec.scheme}://{tspec.host}{port}" + (path if path.startswith("/") else "/" + path)

    def facts_builder(action: Action) -> ActionFacts:
        spec = next((t for t in scope.targets if t.host == action.target_host), None)
        url = target_url(spec) if spec else ""
        return ActionFacts(
            action=action,
            in_scope=validator.check(url).allowed if url else False,
            module_approved=action.module in modules,
            authorization_valid=authorization.is_valid_at(),
            uses_admin_role=False, found_credential_use=False, mass_download=False,
            unexpected_real_data=False, availability_impact=False,
        )

    loop = AgentLoop(run=run, scope=scope, engine=PolicyEngine(policy_version=scope.policy_version),
                     validator=validator, gateway=gateway, vault=vault, orchestrator=orch,
                     budget=budget, facts_builder=facts_builder, org_key=org_key)
    fetch = make_fetch(validator, budget)

    audit("run.start", "ok", f"mode={run.mode.value} targets={len(scope.targets)} modules={','.join(modules)}")
    summary = {"actions": 0, "executed": 0, "blocked": 0, "findings": 0, "evidence": 0, "errors": 0}

    for tspec in scope.targets:
        url = target_url(tspec)
        if True:
            for mod_name in modules:
                if orch.stopped or budget.exceeded():
                    break
                action = Action(
                    organization_id=run.organization_id, run_id=run.id, scope_version_id=scope.id,
                    policy_version=scope.policy_version, target_host=tspec.host, module=mod_name,
                    risk=RiskLevel.READ_ONLY, expected_impact="read one response",
                )
                store.insert("actions", action.model_dump(mode="json"))
                summary["actions"] += 1
                audit("hypothesis", "", f"{mod_name}: observe hardening on {url}")

                # Run the module through the governed loop; capture its result for findings.
                captured: dict = {}

                def capturing_fetch(u: str, _c=captured) -> str:
                    text = fetch(u)
                    _c["text"] = text
                    return text

                try:
                    outcome = loop.step(action, capturing_fetch, target_url=url)
                except Exception as exc:  # network or unexpected
                    summary["errors"] += 1
                    audit("execute", "error", f"{mod_name} {url}: {type(exc).__name__}: {str(exc)[:200]}")
                    continue

                audit("policy", outcome.decision.value, f"{mod_name} {outcome.rule}: {outcome.note[:200]}")
                if not outcome.executed:
                    summary["blocked"] += 1
                    continue
                summary["executed"] += 1

                # Persist redacted evidence created by the loop (last stored item).
                evidence_id = None
                items = vault.list_for_project(organization_id=run.organization_id, project_id=run.project_id)
                if items:
                    ev: Evidence = items[-1]
                    if store.get("evidence", ev.id, organization_id=run.organization_id) is None:
                        store.insert("evidence", ev.model_dump(mode="json"))
                        store.insert("evidence_access_log", {
                            "organization_id": run.organization_id, "evidence_id": ev.id,
                            "actor": actor, "action": "store", "at": _now().isoformat(),
                        })
                        summary["evidence"] += 1
                    evidence_id = ev.id

                # Re-run the module's parser on the captured text to derive observations.
                try:
                    result = PASSIVE_MODULES[mod_name]().run(url, lambda _u, t=captured.get("text", ""): t)
                    audit("observe", "ok", f"{mod_name}: " + "; ".join(result.observations)[:300])
                    finding = _finding_from_observations(run, mod_name, url, result.observations, evidence_id)
                    if finding:
                        store.insert("findings", finding.model_dump(mode="json"))
                        if evidence_id:
                            store.update("evidence", evidence_id, organization_id=run.organization_id,
                                         patch={"finding_id": finding.id})
                        summary["findings"] += 1
                        audit("finding.create", "", f"{finding.id} {finding.title}")
                except RedactionError as exc:
                    audit("evidence.store_refused", "blocked", str(exc)[:200])

    for ev in loop.audit:
        # Loop-level audit entries (policy/observe/ignored_injection) for completeness.
        if ev.decision == "ignored_injection":
            audit("observe", "ignored_injection", ev.detail[:300])

    status = RunStatus.STOPPED if orch.stopped else RunStatus.COMPLETED
    reason = budget.reason_exceeded() or ("" if status is RunStatus.COMPLETED else "stopped")
    store.update("scan_runs", run.id, organization_id=run.organization_id, patch={
        "status": status.value, "stopped_at": _now().isoformat(), "stop_reason": reason,
        "summary": summary, "budget_used": {"requests": budget.requests_made,
                                             "elapsed_seconds": round(budget.elapsed_seconds(), 1)},
    })
    audit("run.finish", status.value, str(summary))
    return summary
