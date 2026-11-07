"""Controlled vocabularies used across the platform.

These mirror the PRD: operating modes (section 5), finding severity /
confidence / status (section 12), action risk and the policy decision set
(sections 7-8).
"""

from __future__ import annotations

from enum import Enum


class OperatingMode(str, Enum):
    """PRD section 5 — modes of operation."""

    PASSIVE = "passive"                 # סקירה פסיבית
    ACTIVE_CONTROLLED = "active"        # אקטיבי מבוקר
    AUTHENTICATED = "authenticated"     # עם הזדהות
    RED_TEAM = "red_team"               # תרחיש צוות אדום


class Environment(str, Enum):
    TEST = "test"
    PRODUCTION = "production"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(str, Enum):
    """PRD section 12 — ביטחון."""

    SUSPECTED = "suspected"             # חשד
    VERIFIED = "verified"               # מאומת
    NEEDS_MANUAL = "needs_manual"       # דורש אימות ידני


class FindingStatus(str, Enum):
    """PRD section 12 — סטטוסים."""

    NEW = "new"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    AWAITING_RETEST = "awaiting_retest"
    FIXED = "fixed"
    ACCEPTED_RISK = "accepted_risk"
    FALSE_POSITIVE = "false_positive"


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    SENSITIVE = "sensitive"
    DESTRUCTIVE = "destructive"


class PolicyDecision(str, Enum):
    """PRD section 8 — default disposition of an action."""

    ALLOW = "allow"                     # אוטומטי
    REQUIRE_APPROVAL = "require_approval"  # דורש אישור פעולה
    BLOCK = "block"                     # חסום
    HALT = "halt"                       # עצירה והתראה


class ScopeVersionStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


class EvidenceKind(str, Enum):
    """PRD section 10.1 — evidence vault entry types."""

    PASSWORD_EXPOSURE = "password_exposure"
    SECRET_EXPOSURE = "secret_exposure"
    INFO_DISCLOSURE = "info_disclosure"
    RECORD_ACCESS = "record_access"
    SCREENSHOT = "screenshot"


class Role(str, Enum):
    """PRD section 3 — roles."""

    ORG_ADMIN = "org_admin"
    SURVEY_MANAGER = "survey_manager"
    PT_TESTER = "pt_tester"
    DEVELOPER = "developer"
    EXECUTIVE = "executive"
    AUDITOR = "auditor"
    CLIENT = "client"
