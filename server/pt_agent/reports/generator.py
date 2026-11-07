"""Report Service — PRD section 13.

Reports are generated *only* from evidence and findings that already exist
(PRD section 15: "דוחות שנוצרים מראיות קיימות בלבד"). The generator never
invents findings, and it distinguishes proven impact, inferred impact and
coverage limitations (acceptance criterion 12). A report that is produced
freezes the exact finding/evidence set used (ReportVersion).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ..evidence import EvidenceVault, assert_clean
from ..models import Confidence, Finding, ReportVersion, ScanRun, Severity

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


def freeze(run: ScanRun, findings: list[Finding]) -> ReportVersion:
    evidence_ids: list[str] = []
    for f in findings:
        evidence_ids.extend(f.evidence_ids)
    return ReportVersion(
        organization_id=run.organization_id,
        project_id=run.project_id,
        run_id=run.id,
        finding_ids=[f.id for f in findings],
        evidence_ids=sorted(set(evidence_ids)),
    )


def _coverage_note(findings: list[Finding]) -> str:
    """No findings is not a certificate of security (PRD section 13)."""
    if not findings:
        return (
            "No findings were recorded. This is **not** a statement that the "
            "system is secure; see coverage and limitations below."
        )
    return ""


def render_markdown(
    run: ScanRun,
    findings: list[Finding],
    vault: EvidenceVault,
    *,
    organization_id: str,
) -> str:
    ordered = sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))
    lines: list[str] = []
    lines.append(f"# Security report — run {run.id}")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    # Executive summary (section 13 — דוח הנהלה).
    lines.append("## Executive summary")
    note = _coverage_note(ordered)
    if note:
        lines.append(note)
    by_sev: dict[str, int] = {}
    for f in ordered:
        by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1
    if by_sev:
        lines.append("")
        lines.append("Findings by severity:")
        for sev in ("critical", "high", "medium", "low"):
            if sev in by_sev:
                lines.append(f"- {sev}: {by_sev[sev]}")
    lines.append("")

    # Technical findings (section 13 — דוח טכני).
    lines.append("## Findings")
    for f in ordered:
        lines.append("")
        lines.append(f"### {f.id} — {f.title}")
        lines.append(f"Severity: {f.severity.value} | Confidence: {f.confidence.value} | Status: {f.status.value}")
        lines.append(f"Asset: {f.asset_path}")
        if f.preconditions:
            lines.append(f"Preconditions: {f.preconditions}")
        if f.expected_result or f.actual_result:
            lines.append(f"Expected: {f.expected_result}")
            lines.append(f"Actual: {f.actual_result}")
        if f.proven_impact:
            lines.append(f"Proven impact: {f.proven_impact}")
        if f.inferred_impact:
            lines.append(f"Inferred impact (not proven): {f.inferred_impact}")
        if f.reproduction:
            lines.append(f"Reproduction: {f.reproduction}")
        if f.remediation:
            lines.append(f"Remediation: {f.remediation}")
        if f.limitations:
            lines.append(f"Limitations: {f.limitations}")
        # Attach redacted evidence only.
        for eid in f.evidence_ids:
            try:
                ev = vault.get(eid, organization_id=organization_id, actor="report")
            except Exception:
                continue
            lines.append(f"Evidence {ev.id} ({ev.kind.value}): {ev.redacted_source}")

    text = "\n".join(lines)
    # Final guard: a report must never carry a raw secret.
    assert_clean(text)
    return text


def render_json(run: ScanRun, findings: list[Finding]) -> str:
    payload = {
        "run_id": run.id,
        "project_id": run.project_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings": [
            {
                "id": f.id,
                "title": f.title,
                "asset": f.asset_path,
                "severity": f.severity.value,
                "confidence": f.confidence.value,
                "status": f.status.value,
                "proven_impact": f.proven_impact,
                "inferred_impact": f.inferred_impact,
                "evidence_ids": f.evidence_ids,
            }
            for f in findings
        ],
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    assert_clean(text)
    return text
