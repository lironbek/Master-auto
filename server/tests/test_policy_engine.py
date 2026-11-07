"""PRD sections 7-8 and acceptance criteria 3, 4, 11."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pt_agent.models import Action, Approval, PolicyDecision, RiskLevel
from pt_agent.policy import ActionFacts, PolicyEngine, fingerprint_action

ORG = "org_aaaa"


def _action(**kw):
    base = dict(
        organization_id=ORG,
        run_id="run_1",
        scope_version_id="scope_1",
        policy_version="policy-v1",
        target_host="app.test.example",
        module="passive.security_headers",
        risk=RiskLevel.READ_ONLY,
    )
    base.update(kw)
    return Action(**base)


def _facts(action, **kw):
    base = dict(
        action=action,
        in_scope=True,
        module_approved=True,
        authorization_valid=True,
        uses_admin_role=False,
        found_credential_use=False,
        mass_download=False,
        unexpected_real_data=False,
        availability_impact=False,
    )
    base.update(kw)
    return ActionFacts(**base)


def test_read_only_in_scope_allowed():
    e = PolicyEngine()
    assert e.evaluate(_facts(_action())).decision is PolicyDecision.ALLOW


def test_out_of_scope_blocked():
    e = PolicyEngine()
    assert e.evaluate(_facts(_action(), in_scope=False)).decision is PolicyDecision.BLOCK


def test_invalid_authorization_blocked():
    e = PolicyEngine()
    assert e.evaluate(_facts(_action(), authorization_valid=False)).decision is PolicyDecision.BLOCK


def test_destructive_blocked_even_with_approval():
    """Acceptance: a human approval never lifts a BLOCK (section 8)."""
    e = PolicyEngine()
    action = _action(risk=RiskLevel.DESTRUCTIVE)
    facts = _facts(action, availability_impact=True)
    approval = _make_approval(action)
    res = e.authorize(facts, approval)
    assert res.decision is PolicyDecision.BLOCK


def test_found_credential_use_blocked():
    e = PolicyEngine()
    assert e.evaluate(_facts(_action(), found_credential_use=True)).decision is PolicyDecision.BLOCK


def test_mass_download_blocked():
    e = PolicyEngine()
    assert e.evaluate(_facts(_action(), mass_download=True)).decision is PolicyDecision.BLOCK


def test_unexpected_real_data_halts():
    e = PolicyEngine()
    assert e.evaluate(_facts(_action(), unexpected_real_data=True)).decision is PolicyDecision.HALT


def test_data_mutation_requires_approval():
    e = PolicyEngine()
    action = _action(risk=RiskLevel.REVERSIBLE_WRITE, changes_data=True)
    res = e.evaluate(_facts(action))
    assert res.decision is PolicyDecision.REQUIRE_APPROVAL


def _make_approval(action, *, valid=True, fp=None):
    return Approval(
        organization_id=ORG,
        run_id=action.run_id,
        action_id=action.id,
        approver_user_id="usr_tester",
        target_host=action.target_host,
        module=action.module,
        valid_until=datetime.now(timezone.utc)
        + (timedelta(hours=1) if valid else -timedelta(hours=1)),
        parameter_fingerprint=fp if fp is not None else fingerprint_action(action),
    )


def test_valid_approval_allows_gated_action():
    e = PolicyEngine()
    action = _action(risk=RiskLevel.SENSITIVE)
    res = e.authorize(_facts(action), _make_approval(action))
    assert res.decision is PolicyDecision.ALLOW


def test_expired_approval_rejected():
    """Acceptance criterion 4 / 9 — expired approval cannot execute."""
    e = PolicyEngine()
    action = _action(risk=RiskLevel.SENSITIVE)
    res = e.authorize(_facts(action), _make_approval(action, valid=False))
    assert res.decision is PolicyDecision.REQUIRE_APPROVAL


def test_changed_parameters_void_approval():
    """Acceptance criterion 4 — material parameter change voids approval."""
    e = PolicyEngine()
    action = _action(risk=RiskLevel.SENSITIVE)
    stale = _make_approval(action, fp="stale-fingerprint")
    res = e.authorize(_facts(action), stale)
    assert res.decision is PolicyDecision.REQUIRE_APPROVAL


def test_approval_bound_to_target_and_module():
    e = PolicyEngine()
    action = _action(risk=RiskLevel.SENSITIVE)
    approval = _make_approval(action)
    approval.target_host = "other.host"
    res = e.authorize(_facts(action), approval)
    assert res.decision is PolicyDecision.REQUIRE_APPROVAL


def test_fail_closed_when_no_rule_matches():
    """Acceptance criterion 11 — unknown classification must not auto-allow."""
    e = PolicyEngine(rules=[])  # empty table
    res = e.evaluate(_facts(_action()))
    assert res.decision is PolicyDecision.REQUIRE_APPROVAL
    assert res.rule == "default_deny"
