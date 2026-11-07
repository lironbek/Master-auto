"""Default action policy table — PRD section 8.

Each rule maps a classified action to its default disposition. The table is
ordered; the first matching rule wins. ``HALT`` and ``BLOCK`` dispositions can
never be overridden by a human approval or by text coming from the target
(PRD section 8: "אישור אנושי אינו עוקף חסימה").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..models import Action, PolicyDecision, RiskLevel


@dataclass(frozen=True)
class Rule:
    name: str
    decision: PolicyDecision
    predicate: Callable[["ActionFacts"], bool]
    rationale: str


@dataclass(frozen=True)
class ActionFacts:
    """Flattened, trusted facts about an action, derived server-side.

    These are computed by the orchestrator, never taken from model output or
    target content.
    """

    action: Action
    in_scope: bool                 # egress validator says target is approved
    module_approved: bool          # module is in ScopeVersion.allowed_modules
    authorization_valid: bool      # Authorization valid at action time
    uses_admin_role: bool
    found_credential_use: bool     # attempts to use a discovered secret
    mass_download: bool
    unexpected_real_data: bool
    availability_impact: bool      # DoS / load / deletion


DEFAULT_RULES: list[Rule] = [
    # --- Unconditional blocks (section 8, section 2 out-of-scope) ---
    Rule(
        "authorization_invalid",
        PolicyDecision.BLOCK,
        lambda f: not f.authorization_valid,
        "No valid authorization document for the action window.",
    ),
    Rule(
        "out_of_scope_target",
        PolicyDecision.BLOCK,
        lambda f: not f.in_scope,
        "Target is outside the approved scope.",
    ),
    Rule(
        "availability_impact",
        PolicyDecision.BLOCK,
        lambda f: f.availability_impact or f.action.risk is RiskLevel.DESTRUCTIVE,
        "Destructive actions and availability impact are out of product scope.",
    ),
    Rule(
        "found_credential_use",
        PolicyDecision.BLOCK,
        lambda f: f.found_credential_use,
        "Using a discovered password/secret is prohibited.",
    ),
    Rule(
        "mass_download",
        PolicyDecision.BLOCK,
        lambda f: f.mass_download,
        "Mass download / data exfiltration is prohibited.",
    ),
    # --- Halt-and-alert (section 8, section 10) ---
    Rule(
        "unexpected_real_data",
        PolicyDecision.HALT,
        lambda f: f.unexpected_real_data,
        "Unexpected real data encountered — halt and alert the survey manager.",
    ),
    # --- Approval-gated (section 8) ---
    Rule(
        "module_not_approved",
        PolicyDecision.REQUIRE_APPROVAL,
        lambda f: not f.module_approved,
        "Active module is not on the approved module list.",
    ),
    Rule(
        "admin_role_use",
        PolicyDecision.REQUIRE_APPROVAL,
        lambda f: f.uses_admin_role,
        "Use of a supplied admin role requires explicit, scenario-limited approval.",
    ),
    Rule(
        "data_mutation",
        PolicyDecision.REQUIRE_APPROVAL,
        lambda f: f.action.changes_data
        or f.action.risk is RiskLevel.REVERSIBLE_WRITE,
        "Creating or changing test data requires approval and a cleanup plan.",
    ),
    Rule(
        "sensitive_action",
        PolicyDecision.REQUIRE_APPROVAL,
        lambda f: f.action.risk is RiskLevel.SENSITIVE,
        "Sensitive action requires tester approval.",
    ),
    # --- Default allow (section 8: browse/map/read within budget) ---
    Rule(
        "read_within_scope",
        PolicyDecision.ALLOW,
        lambda f: f.action.risk is RiskLevel.READ_ONLY,
        "Read-only action within approved, in-scope target and budget.",
    ),
]

# Dispositions a human approval can never lift.
NON_OVERRIDABLE = {PolicyDecision.BLOCK, PolicyDecision.HALT}
