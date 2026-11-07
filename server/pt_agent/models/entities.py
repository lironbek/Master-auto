"""Core data model — PRD section 16.

Every business entity carries ``organization_id`` so tenant isolation can be
enforced server-side and in storage, not only in the UI (PRD section 3). These
are Pydantic models used as the in-memory reference schema; a production
deployment would back them with a database that keeps the same invariants.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .enums import (
    Confidence,
    Environment,
    EvidenceKind,
    FindingStatus,
    OperatingMode,
    RiskLevel,
    Role,
    RunStatus,
    ScopeVersionStatus,
    Severity,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OrgScoped(BaseModel):
    """Base for every tenant-owned entity."""

    organization_id: str
    created_at: datetime = Field(default_factory=_now)


class Organization(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("org"))
    name: str
    created_at: datetime = Field(default_factory=_now)


class User(OrgScoped):
    id: str = Field(default_factory=lambda: _new_id("usr"))
    email: str
    display_name: str = ""


class Membership(OrgScoped):
    id: str = Field(default_factory=lambda: _new_id("mem"))
    user_id: str
    role: Role


class Project(OrgScoped):
    id: str = Field(default_factory=lambda: _new_id("prj"))
    name: str
    description: str = ""


class Asset(OrgScoped):
    """A system the project is permitted to look at."""

    id: str = Field(default_factory=lambda: _new_id("ast"))
    project_id: str
    label: str
    owner_contact: str = ""


class Authorization(OrgScoped):
    """PRD section 4 — מסמך הרשאה. Proof that a human with authority
    permitted testing. Control verification (DNS/file) does *not* replace it."""

    id: str = Field(default_factory=lambda: _new_id("auth"))
    project_id: str
    approver_name: str
    approver_authority: str
    valid_from: datetime
    valid_until: datetime
    control_verified: bool = False  # DNS or file proof of control
    document_reference: str = ""

    def is_valid_at(self, when: Optional[datetime] = None) -> bool:
        when = when or _now()
        return self.valid_from <= when <= self.valid_until


class TargetSpec(BaseModel):
    """An allowed target. Subdomains are NOT implied — each is listed
    explicitly (PRD section 9)."""

    scheme: str                         # http | https
    host: str                           # exact hostname, no wildcard
    ports: list[int] = Field(default_factory=lambda: [443])
    allowed_paths: list[str] = Field(default_factory=lambda: ["/"])


class Exclusion(BaseModel):
    """PRD section 4 — החרגות: payments, message delivery, third parties,
    forbidden paths."""

    kind: str
    pattern: str
    note: str = ""


class RunBudget(BaseModel):
    """PRD section 5 — pilot defaults. The first limit reached stops the run."""

    max_duration_seconds: int = 30 * 60
    max_requests: int = 1000
    requests_per_second: float = 1.0
    max_concurrency_per_host: int = 2
    max_response_bytes: int = 5_000_000
    max_model_cost_usd: float = 25.0


class TestAccountRef(OrgScoped):
    """Reference to a synthetic test account held in the Secrets Vault.
    The credential value itself never lives here or reaches the model."""

    id: str = Field(default_factory=lambda: _new_id("acct"))
    project_id: str
    label: str
    role_label: str
    org_context: str = ""
    vault_ref: str = ""  # opaque handle into the Secrets Vault


class ScopeVersion(OrgScoped):
    """PRD section 4 — חוזה בדיקה. A run binds to one approved version.
    Any scope change creates a new version (section 4)."""

    id: str = Field(default_factory=lambda: _new_id("scope"))
    project_id: str
    version: int
    status: ScopeVersionStatus = ScopeVersionStatus.DRAFT
    authorization_id: str
    environment: Environment = Environment.TEST
    targets: list[TargetSpec] = Field(default_factory=list)
    exclusions: list[Exclusion] = Field(default_factory=list)
    allowed_modules: list[str] = Field(default_factory=list)
    allowed_modes: list[OperatingMode] = Field(
        default_factory=lambda: [OperatingMode.PASSIVE]
    )
    budget: RunBudget = Field(default_factory=RunBudget)
    run_window_start: Optional[datetime] = None
    run_window_end: Optional[datetime] = None
    stop_conditions: list[str] = Field(default_factory=list)
    policy_version: str = "policy-v1"
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class ScanRun(OrgScoped):
    id: str = Field(default_factory=lambda: _new_id("run"))
    project_id: str
    scope_version_id: str
    mode: OperatingMode
    status: RunStatus = RunStatus.CREATED
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    stop_reason: str = ""


class Hypothesis(OrgScoped):
    id: str = Field(default_factory=lambda: _new_id("hyp"))
    run_id: str
    statement: str
    rationale: str
    expected_evidence: str
    resolved: bool = False


class Action(OrgScoped):
    """PRD section 7 — חוזה פעולה. The full context attached to every
    proposed action before the Policy Engine decides."""

    id: str = Field(default_factory=lambda: _new_id("act"))
    run_id: str
    scope_version_id: str
    policy_version: str
    target_host: str
    module: str
    test_account_id: Optional[str] = None
    hypothesis_id: Optional[str] = None
    risk: RiskLevel = RiskLevel.READ_ONLY
    expected_impact: str = ""
    changes_data: bool = False
    cleanup_plan: str = ""
    approval_id: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)


class Approval(OrgScoped):
    """PRD section 8 — bound to run, target, action and a time validity.
    A change to material parameters voids it."""

    id: str = Field(default_factory=lambda: _new_id("apr"))
    run_id: str
    action_id: str
    approver_user_id: str
    target_host: str
    module: str
    valid_until: datetime
    parameter_fingerprint: str
    revoked: bool = False


class Evidence(OrgScoped):
    """PRD sections 10.1 / 10.4. Stores only redacted proof. The raw secret
    value is never persisted — ``redacted_fingerprint`` is an HMAC."""

    id: str = Field(default_factory=lambda: _new_id("evi"))
    project_id: str
    finding_id: Optional[str] = None
    kind: EvidenceKind
    sensitivity: str = "high"
    redacted_source: str                 # already-redacted snippet
    redacted_fingerprint: str = ""       # HMAC, never the raw value
    checksum: str = ""                   # checksum of the redacted artifact
    redaction_policy_version: str = "redaction-v1"
    captured_at: datetime = Field(default_factory=_now)
    delete_at: Optional[datetime] = None


class Finding(OrgScoped):
    """PRD section 12 — structure of a finding."""

    id: str = Field(default_factory=lambda: _new_id("find"))
    project_id: str
    run_id: str
    title: str
    asset_path: str
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
    status: FindingStatus = FindingStatus.NEW
    owner: str = ""
    due_date: Optional[datetime] = None
    duplicate_of: Optional[str] = None


class FindingEvent(OrgScoped):
    id: str = Field(default_factory=lambda: _new_id("fev"))
    finding_id: str
    actor: str
    event: str
    at: datetime = Field(default_factory=_now)


class AuditEvent(OrgScoped):
    """Tamper-evident audit log — never contains raw secrets (PRD section 19)."""

    id: str = Field(default_factory=lambda: _new_id("aud"))
    run_id: Optional[str] = None
    actor: str
    action: str
    decision: str = ""
    policy_version: str = ""
    detail: str = ""
    at: datetime = Field(default_factory=_now)


class ReportVersion(OrgScoped):
    """PRD section 13 / 16 — freezes the findings and evidence used to render."""

    id: str = Field(default_factory=lambda: _new_id("rep"))
    project_id: str
    run_id: str
    finding_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
