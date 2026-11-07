"""PRD section 10.1-10.4 and acceptance criteria 2, 3, 6."""

from __future__ import annotations

import pytest

from pt_agent.evidence import EvidenceVault, RedactionError, VaultAccessError
from pt_agent.models import EvidenceKind

ORG_A = "org_aaaa"
ORG_B = "org_bbbb"
ORG_KEY = b"test-org-hmac-key-32-bytes-long!!"


def _vault():
    return EvidenceVault(retention_days=30)


def test_stored_evidence_has_no_raw_secret():
    v = _vault()
    ev = v.store(
        organization_id=ORG_A,
        project_id="prj_1",
        kind=EvidenceKind.PASSWORD_EXPOSURE,
        raw_snippet="password=TopSecret42 in body",
        org_key=ORG_KEY,
    )
    assert "TopSecret42" not in ev.redacted_source
    assert ev.checksum


def test_cross_org_access_denied():
    """Acceptance criterion 2 — org A cannot read org B evidence."""
    v = _vault()
    ev = v.store(
        organization_id=ORG_B,
        project_id="prj_b",
        kind=EvidenceKind.INFO_DISCLOSURE,
        raw_snippet="some header info",
        org_key=ORG_KEY,
    )
    with pytest.raises(VaultAccessError):
        v.get(ev.id, organization_id=ORG_A, actor="attacker")


def test_deleted_evidence_not_viewable_via_old_id():
    """Acceptance criterion 3 — deleted evidence is gone for old links."""
    v = _vault()
    ev = v.store(
        organization_id=ORG_A,
        project_id="prj_1",
        kind=EvidenceKind.INFO_DISCLOSURE,
        raw_snippet="info",
        org_key=ORG_KEY,
    )
    v.delete(ev.id, organization_id=ORG_A, actor="mgr")
    with pytest.raises(VaultAccessError):
        v.get(ev.id, organization_id=ORG_A, actor="mgr")


def test_access_is_logged():
    v = _vault()
    ev = v.store(
        organization_id=ORG_A,
        project_id="prj_1",
        kind=EvidenceKind.INFO_DISCLOSURE,
        raw_snippet="info",
        org_key=ORG_KEY,
    )
    v.get(ev.id, organization_id=ORG_A, actor="viewer")
    v.download(ev.id, organization_id=ORG_A, actor="viewer")
    actions = [e.action for e in v.access_log]
    assert "store" in actions and "view" in actions and "download" in actions
    # The log never copies evidence content.
    assert all(not hasattr(e, "content") for e in v.access_log)
