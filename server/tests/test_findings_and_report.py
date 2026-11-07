"""PRD sections 12-13 and acceptance criteria 5, 8, 12."""

from __future__ import annotations

import pytest

from pt_agent.evidence import EvidenceVault
from pt_agent.findings import FindingsService, InvalidTransition
from pt_agent.models import (
    Confidence,
    EvidenceKind,
    Finding,
    FindingStatus,
    ScanRun,
    Severity,
)
from pt_agent.reports import render_json, render_markdown

ORG = "org_aaaa"
ORG_KEY = b"test-org-hmac-key-32-bytes-long!!"


def _finding(**kw):
    base = dict(
        organization_id=ORG,
        project_id="prj_1",
        run_id="run_1",
        title="Cross-tenant read",
        asset_path="/api/docs/1",
        category="authz",
        severity=Severity.HIGH,
    )
    base.update(kw)
    return Finding(**base)


def test_dedup_merges_and_links():
    svc = FindingsService()
    a = svc.add(_finding(evidence_ids=["evi_1"]))
    # A duplicate resolves to the canonical finding and merges its evidence.
    returned = svc.add(_finding(evidence_ids=["evi_2"]))
    assert returned.id == a.id
    assert "evi_1" in a.evidence_ids and "evi_2" in a.evidence_ids
    # The duplicate record itself is stored with a link back to the original.
    dup = next(f for f in svc._by_id.values() if f.duplicate_of)
    assert dup.duplicate_of == a.id


def test_invalid_status_transition_rejected():
    svc = FindingsService()
    f = svc.add(_finding())
    with pytest.raises(InvalidTransition):
        svc.transition(f.id, FindingStatus.FIXED)  # NEW -> FIXED not allowed


def test_verified_requires_evidence():
    """Acceptance criterion 5."""
    svc = FindingsService()
    f = _finding(confidence=Confidence.VERIFIED, evidence_ids=[])
    with pytest.raises(ValueError):
        svc.require_evidence_for_verified(f)


def test_report_distinguishes_proven_and_inferred():
    """Acceptance criterion 12."""
    run = ScanRun(organization_id=ORG, project_id="prj_1", scope_version_id="s", mode="passive")
    vault = EvidenceVault()
    ev = vault.store(
        organization_id=ORG,
        project_id="prj_1",
        kind=EvidenceKind.RECORD_ACCESS,
        raw_snippet="synthetic marker MARKER-123",
        org_key=ORG_KEY,
    )
    f = _finding(
        confidence=Confidence.VERIFIED,
        evidence_ids=[ev.id],
        proven_impact="read one synthetic doc across tenants",
        inferred_impact="other docs may be exposed; not tested",
    )
    md = render_markdown(run, [f], vault, organization_id=ORG)
    assert "Proven impact:" in md
    assert "Inferred impact (not proven):" in md


def test_empty_report_is_not_a_clean_bill():
    """Acceptance: no findings != secure (section 13)."""
    run = ScanRun(organization_id=ORG, project_id="prj_1", scope_version_id="s", mode="passive")
    md = render_markdown(run, [], EvidenceVault(), organization_id=ORG)
    assert "not" in md.lower() and "secure" in md.lower()


def test_report_json_valid():
    run = ScanRun(organization_id=ORG, project_id="prj_1", scope_version_id="s", mode="passive")
    import json

    payload = json.loads(render_json(run, [_finding()]))
    assert payload["run_id"] == run.id
    assert payload["findings"][0]["severity"] == "high"
