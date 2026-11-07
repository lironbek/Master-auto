"""Agent workflow skeleton — PRD section 7 (מחזור עבודה).

This wires the governance components into the 9-step loop. The planning step
(hypothesis generation) is represented by an injected ``planner`` callable so
the loop can be exercised deterministically in tests without a live model. The
loop enforces: policy decision before every action, egress validation, budget,
and stop on sufficient proof or budget exhaustion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..evidence import EvidenceVault
from ..models import (
    Action,
    Approval,
    AuditEvent,
    EvidenceKind,
    PolicyDecision,
    ScanRun,
    ScopeVersion,
)
from ..orchestrator import BudgetState, Orchestrator
from ..policy import ActionFacts, PolicyEngine
from ..scope import EgressValidator
from .gateway import FetchFn, ToolGateway
from .untrusted import scan_untrusted


@dataclass
class StepOutcome:
    action: Action
    decision: PolicyDecision
    rule: str
    executed: bool
    note: str = ""


FactsBuilder = Callable[[Action], ActionFacts]


class AgentLoop:
    """One run's worth of plan -> policy -> execute -> evaluate cycles."""

    def __init__(
        self,
        *,
        run: ScanRun,
        scope: ScopeVersion,
        engine: PolicyEngine,
        validator: EgressValidator,
        gateway: ToolGateway,
        vault: EvidenceVault,
        orchestrator: Orchestrator,
        budget: BudgetState,
        facts_builder: FactsBuilder,
        org_key: bytes | None = None,
    ):
        self.run = run
        self.scope = scope
        self.engine = engine
        self.validator = validator
        self.gateway = gateway
        self.vault = vault
        self.orchestrator = orchestrator
        self.budget = budget
        self.facts_builder = facts_builder
        self.org_key = org_key
        self.audit: list[AuditEvent] = []

    def _log(self, action: str, decision: str = "", detail: str = "") -> None:
        self.audit.append(
            AuditEvent(
                organization_id=self.run.organization_id,
                run_id=self.run.id,
                actor="agent",
                action=action,
                decision=decision,
                policy_version=self.engine.policy_version,
                detail=detail,
            )
        )

    def step(
        self,
        action: Action,
        fetch: FetchFn,
        *,
        approval: Optional[Approval] = None,
        target_url: str = "",
    ) -> StepOutcome:
        # Budget / stop gate (steps 9).
        reason = self.budget.reason_exceeded()
        if reason or self.orchestrator.stopped:
            self._log("skip", "stopped", reason or "run stopped")
            return StepOutcome(action, PolicyDecision.BLOCK, "stopped", False, reason or "stopped")

        # Policy decision before action (steps 5-6).
        facts = self.facts_builder(action)
        result = self.engine.authorize(facts, approval)
        self._log("policy", result.decision.value, f"{result.rule}: {result.rationale}")

        if result.decision is not PolicyDecision.ALLOW:
            if result.decision is PolicyDecision.HALT:
                self.orchestrator.pause(self.run, "halt: unexpected exposure")
            return StepOutcome(action, result.decision, result.rule, False, result.rationale)

        # Execute only through the gateway (step 6).
        url = target_url or f"{self.scope.targets[0].scheme}://{action.target_host}"
        try:
            mod_result = self.gateway.run(action.module, url, fetch)
        except Exception as exc:  # gateway/egress refusal
            self._log("execute", "error", str(exc))
            return StepOutcome(action, PolicyDecision.BLOCK, "gateway_error", False, str(exc))

        self.budget.charge_request(response_bytes=len(mod_result.raw_for_redaction))

        # Untrusted content never steers the loop (section 7).
        injection = scan_untrusted(mod_result.raw_for_redaction)
        if injection.detected:
            self._log("observe", "ignored_injection", injection.as_observation())

        # Store redacted evidence (step 7-8). Redaction happens in the vault.
        if mod_result.observations:
            self.vault.store(
                organization_id=self.run.organization_id,
                project_id=self.run.project_id,
                kind=EvidenceKind.INFO_DISCLOSURE,
                raw_snippet=mod_result.raw_for_redaction,
                org_key=self.org_key,
                actor="agent",
            )

        self._log("execute", "ok", f"module={action.module} target={action.target_host}")
        return StepOutcome(action, PolicyDecision.ALLOW, result.rule, True, "executed")
