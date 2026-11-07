"""Findings service — PRD section 12.

Creates findings, enforces the status lifecycle, and deduplicates while
preserving evidence and links back to the originals.
"""

from __future__ import annotations

from ..models import Confidence, Finding, FindingStatus

# Allowed status transitions (PRD section 12 status list).
_TRANSITIONS: dict[FindingStatus, set[FindingStatus]] = {
    FindingStatus.NEW: {FindingStatus.IN_REVIEW, FindingStatus.FALSE_POSITIVE},
    FindingStatus.IN_REVIEW: {
        FindingStatus.APPROVED,
        FindingStatus.FALSE_POSITIVE,
        FindingStatus.NEW,
    },
    FindingStatus.APPROVED: {FindingStatus.IN_PROGRESS, FindingStatus.ACCEPTED_RISK},
    FindingStatus.IN_PROGRESS: {FindingStatus.AWAITING_RETEST, FindingStatus.ACCEPTED_RISK},
    FindingStatus.AWAITING_RETEST: {FindingStatus.FIXED, FindingStatus.IN_PROGRESS},
    FindingStatus.FIXED: set(),
    FindingStatus.ACCEPTED_RISK: set(),
    FindingStatus.FALSE_POSITIVE: set(),
}


class InvalidTransition(ValueError):
    pass


def dedup_key(finding: Finding) -> tuple[str, str, str]:
    """Findings collide when they share category, asset path and title."""
    return (finding.category, finding.asset_path, finding.title)


class FindingsService:
    def __init__(self) -> None:
        self._by_id: dict[str, Finding] = {}
        self._by_key: dict[tuple[str, str, str], str] = {}

    def add(self, finding: Finding) -> Finding:
        key = dedup_key(finding)
        existing_id = self._by_key.get(key)
        if existing_id:
            existing = self._by_id[existing_id]
            # Merge evidence, keep a link to the original (section 12).
            for eid in finding.evidence_ids:
                if eid not in existing.evidence_ids:
                    existing.evidence_ids.append(eid)
            finding.duplicate_of = existing_id
            self._by_id[finding.id] = finding
            return existing
        self._by_id[finding.id] = finding
        self._by_key[key] = finding.id
        return finding

    def get(self, finding_id: str) -> Finding:
        return self._by_id[finding_id]

    def transition(self, finding_id: str, new_status: FindingStatus) -> Finding:
        finding = self._by_id[finding_id]
        allowed = _TRANSITIONS.get(finding.status, set())
        if new_status not in allowed:
            raise InvalidTransition(
                f"{finding.status.value} -> {new_status.value} is not allowed"
            )
        finding.status = new_status
        return finding

    @staticmethod
    def require_evidence_for_verified(finding: Finding) -> None:
        """A verified finding must carry evidence (acceptance criterion 5)."""
        if finding.confidence is Confidence.VERIFIED and not finding.evidence_ids:
            raise ValueError("a verified finding must reference evidence")
