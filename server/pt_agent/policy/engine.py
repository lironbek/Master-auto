"""Policy Engine — PRD sections 7-8.

A binding decision is produced before every action. The engine is the only
component allowed to authorise an action; the AI planner may only *propose*
one. An approval that arrived inside target content or model output is never a
valid approval (PRD section 7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..models import Action, Approval, PolicyDecision
from .rules import DEFAULT_RULES, NON_OVERRIDABLE, ActionFacts, Rule


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    rule: str
    rationale: str
    requires_human: bool

    @property
    def permitted(self) -> bool:
        return self.decision is PolicyDecision.ALLOW


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PolicyEngine:
    def __init__(self, rules: Optional[list[Rule]] = None, *, policy_version: str = "policy-v1"):
        self.rules = rules if rules is not None else DEFAULT_RULES
        self.policy_version = policy_version

    def evaluate(self, facts: ActionFacts) -> PolicyResult:
        for rule in self.rules:
            if rule.predicate(facts):
                return PolicyResult(
                    decision=rule.decision,
                    rule=rule.name,
                    rationale=rule.rationale,
                    requires_human=rule.decision is PolicyDecision.REQUIRE_APPROVAL,
                )
        # No rule matched — fail closed.
        return PolicyResult(
            decision=PolicyDecision.REQUIRE_APPROVAL,
            rule="default_deny",
            rationale="No rule matched; defaulting to human approval (fail closed).",
            requires_human=True,
        )

    def authorize(
        self,
        facts: ActionFacts,
        approval: Optional[Approval] = None,
        *,
        now: Optional[datetime] = None,
    ) -> PolicyResult:
        """Combine the rule decision with any supplied approval.

        A BLOCK/HALT decision is returned unchanged regardless of approval. A
        REQUIRE_APPROVAL decision becomes ALLOW only with a valid, matching,
        unexpired approval bound to this action/target/module.
        """
        base = self.evaluate(facts)
        if base.decision in NON_OVERRIDABLE:
            return base
        if base.decision is PolicyDecision.ALLOW:
            return base

        # REQUIRE_APPROVAL path.
        if approval is None:
            return base
        if not self._approval_matches(facts.action, approval, now=now):
            return PolicyResult(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                rule=base.rule,
                rationale="Approval does not match action/target/module or has expired.",
                requires_human=True,
            )
        return PolicyResult(
            decision=PolicyDecision.ALLOW,
            rule=f"{base.rule}+approval",
            rationale="Approved by human for this bound action.",
            requires_human=False,
        )

    @staticmethod
    def _approval_matches(
        action: Action, approval: Approval, *, now: Optional[datetime] = None
    ) -> bool:
        now = now or _now()
        if approval.revoked:
            return False
        if approval.action_id != action.id:
            return False
        if approval.run_id != action.run_id:
            return False
        if approval.target_host != action.target_host:
            return False
        if approval.module != action.module:
            return False
        if approval.valid_until < now:
            return False
        # A change to material parameters voids the approval (section 8).
        if approval.parameter_fingerprint != fingerprint_action(action):
            return False
        return True


def fingerprint_action(action: Action) -> str:
    """Stable fingerprint of an action's material parameters.

    Used to bind an approval to an exact action; changing any material field
    changes the fingerprint and voids the approval (PRD section 8).
    """
    import hashlib

    material = "|".join(
        [
            action.run_id,
            action.scope_version_id,
            action.target_host,
            action.module,
            action.risk.value,
            str(action.changes_data),
            action.test_account_id or "",
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
