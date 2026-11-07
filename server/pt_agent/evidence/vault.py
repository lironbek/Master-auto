"""Evidence vault — PRD sections 10.1-10.4.

A per-project store of *redacted* proof. It never stores an active password or a
full key, and never collects more data to fill itself. Access is checked
server-side on every read/download, scoped to organisation and project
(acceptance criteria 2 and 3). Views, downloads and deletions are logged without
copying evidence content into the log (section 10.2).

This reference implementation keeps evidence in memory; the production
Evidence Service would persist encrypted-at-rest with separate key management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Optional

from ..models import Evidence, EvidenceKind
from .redaction import RedactionError, assert_clean, redact


def _now() -> datetime:
    return datetime.now(timezone.utc)


class VaultAccessError(PermissionError):
    """Cross-tenant or unauthorised access attempt."""


@dataclass
class AccessLogEntry:
    evidence_id: str
    actor: str
    action: str           # view | download | delete | store
    at: datetime = field(default_factory=_now)


class EvidenceVault:
    def __init__(self, *, retention_days: int = 30):
        self._items: dict[str, Evidence] = {}
        self._deleted: set[str] = set()
        self.access_log: list[AccessLogEntry] = []
        self.retention_days = retention_days

    # -- storage -----------------------------------------------------------
    def store(
        self,
        *,
        organization_id: str,
        project_id: str,
        kind: EvidenceKind,
        raw_snippet: str,
        org_key: bytes | None = None,
        actor: str = "system",
        finding_id: Optional[str] = None,
        sensitivity: str = "high",
    ) -> Evidence:
        """Redact *raw_snippet* and store the result.

        Redaction runs before anything is persisted. If it cannot guarantee a
        clean artifact, the store is refused (fail closed).
        """
        try:
            red = redact(raw_snippet, org_key=org_key)
            assert_clean(red.text)
        except RedactionError as exc:
            raise RedactionError(f"refusing to store evidence: {exc}") from exc

        fp = ""
        if red.fingerprints:
            # One representative fingerprint for recurrence comparison.
            first_kind = next(iter(red.fingerprints))
            fp = red.fingerprints[first_kind][0]

        checksum = sha256(red.text.encode("utf-8")).hexdigest()
        evidence = Evidence(
            organization_id=organization_id,
            project_id=project_id,
            finding_id=finding_id,
            kind=kind,
            sensitivity=sensitivity,
            redacted_source=red.text,
            redacted_fingerprint=fp,
            checksum=checksum,
            delete_at=_now() + timedelta(days=self.retention_days),
        )
        self._items[evidence.id] = evidence
        self.access_log.append(AccessLogEntry(evidence.id, actor, "store"))
        return evidence

    # -- access ------------------------------------------------------------
    def _guard(self, evidence: Evidence, organization_id: str) -> None:
        if evidence.organization_id != organization_id:
            raise VaultAccessError("cross-organization access denied")

    def get(self, evidence_id: str, *, organization_id: str, actor: str) -> Evidence:
        if evidence_id in self._deleted or evidence_id not in self._items:
            # A deleted evidence item is not viewable via an old link (AC 3).
            raise VaultAccessError("evidence not found or deleted")
        evidence = self._items[evidence_id]
        self._guard(evidence, organization_id)
        self.access_log.append(AccessLogEntry(evidence_id, actor, "view"))
        return evidence

    def download(self, evidence_id: str, *, organization_id: str, actor: str) -> str:
        evidence = self.get(evidence_id, organization_id=organization_id, actor=actor)
        self.access_log.append(AccessLogEntry(evidence_id, actor, "download"))
        return evidence.redacted_source

    def delete(self, evidence_id: str, *, organization_id: str, actor: str) -> None:
        if evidence_id not in self._items:
            return
        evidence = self._items[evidence_id]
        self._guard(evidence, organization_id)
        # Deleting also removes derived artifacts and indexes (section 10.4);
        # here that is the single stored record plus any cached lookup.
        self._deleted.add(evidence_id)
        del self._items[evidence_id]
        self.access_log.append(AccessLogEntry(evidence_id, actor, "delete"))

    def list_for_project(self, *, organization_id: str, project_id: str) -> list[Evidence]:
        return [
            e
            for e in self._items.values()
            if e.organization_id == organization_id and e.project_id == project_id
        ]
