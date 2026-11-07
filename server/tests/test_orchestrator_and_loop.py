"""PRD sections 5, 7, 18 and acceptance criteria 7, 10."""

from __future__ import annotations

from datetime import timedelta

import pytest

from pt_agent.agent import AgentLoop, CookieFlagsModule, SecurityHeadersModule, ToolGateway
from pt_agent.evidence import EvidenceVault
from pt_agent.models import Action, OperatingMode, RiskLevel
from pt_agent.orchestrator import BudgetState, Orchestrator, RunError
from pt_agent.policy import ActionFacts, PolicyEngine
from pt_agent.scope import EgressValidator

ORG = "org_aaaa"
ORG_KEY = b"test-org-hmac-key-32-bytes-long!!"


def test_run_requires_approved_scope(scope, authorization):
    from pt_agent.models import ScopeVersionStatus

    scope.status = ScopeVersionStatus.DRAFT
    orch = Orchestrator()
    with pytest.raises(RunError):
        orch.open_run(scope, authorization, OperatingMode.PASSIVE)


def test_run_rejects_disallowed_mode(scope, authorization):
    orch = Orchestrator()
    with pytest.raises(RunError):
        orch.open_run(scope, authorization, OperatingMode.RED_TEAM)


def test_stop_cuts_egress(scope, authorization):
    """Acceptance criterion 7 — stop severs egress."""
    cut = {"done": False}

    def shutdown():
        cut["done"] = True

    orch = Orchestrator(egress_shutdown=shutdown)
    run = orch.open_run(scope, authorization, OperatingMode.PASSIVE)
    orch.stop(run, "operator stop")
    assert cut["done"] is True
    assert orch.stopped
    assert run.status.value == "stopped"


def test_expired_authorization_stops_run(scope, authorization, now):
    orch = Orchestrator()
    run = orch.open_run(scope, authorization, OperatingMode.PASSIVE)
    with pytest.raises(RunError):
        orch.guard_authorization(run, authorization, now=now + timedelta(hours=2))
    assert run.status.value == "stopped"


def test_budget_stops_run(scope):
    b = BudgetState(budget=scope.budget)
    for _ in range(scope.budget.max_requests):
        b.charge_request()
    assert b.exceeded()
    assert "request budget" in b.reason_exceeded()


def _facts_builder(scope):
    def build(action: Action) -> ActionFacts:
        return ActionFacts(
            action=action,
            in_scope=True,
            module_approved=action.module in scope.allowed_modules,
            authorization_valid=True,
            uses_admin_role=False,
            found_credential_use=False,
            mass_download=False,
            unexpected_real_data=False,
            availability_impact=False,
        )

    return build


def test_loop_executes_allowed_passive_module(scope, authorization):
    orch = Orchestrator()
    run = orch.open_run(scope, authorization, OperatingMode.PASSIVE)
    validator = EgressValidator(scope)
    gateway = ToolGateway(validator)
    gateway.register(SecurityHeadersModule())
    gateway.register(CookieFlagsModule())
    vault = EvidenceVault()

    loop = AgentLoop(
        run=run,
        scope=scope,
        engine=PolicyEngine(),
        validator=validator,
        gateway=gateway,
        vault=vault,
        orchestrator=orch,
        budget=BudgetState(budget=scope.budget),
        facts_builder=_facts_builder(scope),
        org_key=ORG_KEY,
    )

    action = Action(
        organization_id=ORG,
        run_id=run.id,
        scope_version_id=scope.id,
        policy_version="policy-v1",
        target_host="app.test.example",
        module="passive.security_headers",
        risk=RiskLevel.READ_ONLY,
    )

    def fetch(url: str) -> str:
        return "HTTP/1.1 200 OK\nContent-Type: text/html\n\n<html>hi</html>"

    outcome = loop.step(action, fetch, target_url="https://app.test.example/")
    assert outcome.executed
    assert outcome.decision.value == "allow"


def test_loop_blocks_out_of_scope_target(scope, authorization):
    orch = Orchestrator()
    run = orch.open_run(scope, authorization, OperatingMode.PASSIVE)
    validator = EgressValidator(scope)
    gateway = ToolGateway(validator)
    gateway.register(SecurityHeadersModule())

    loop = AgentLoop(
        run=run,
        scope=scope,
        engine=PolicyEngine(),
        validator=validator,
        gateway=gateway,
        vault=EvidenceVault(),
        orchestrator=orch,
        budget=BudgetState(budget=scope.budget),
        facts_builder=_facts_builder(scope),
        org_key=ORG_KEY,
    )
    action = Action(
        organization_id=ORG,
        run_id=run.id,
        scope_version_id=scope.id,
        policy_version="policy-v1",
        target_host="evil.example",
        module="passive.security_headers",
        risk=RiskLevel.READ_ONLY,
    )
    outcome = loop.step(action, lambda u: "", target_url="https://evil.example/")
    assert not outcome.executed
