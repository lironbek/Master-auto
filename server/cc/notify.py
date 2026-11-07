"""Outbound notifications for alerts and bad scan grades.

Optional, configured by environment on the server:
- CC_ALERT_WEBHOOK_URL   POST a JSON payload (n8n / Slack-compatible / any HTTPS endpoint)
- RESEND_API_KEY + CC_ALERT_EMAIL_TO [+ CC_ALERT_EMAIL_FROM]   send an email through Resend

Never raises and never blocks the caller for more than a few seconds; a failed
delivery is recorded as an audit event so it is visible, not silent.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from pt_agent.models import AuditEvent


def _audit(store, org_id: str, action: str, decision: str, detail: str) -> None:
    try:
        store.insert("audit_events", AuditEvent(organization_id=org_id, actor="notifier", action=action, decision=decision,
                                                detail=detail[:500]).model_dump(mode="json"))
    except Exception:
        pass


def send(*, store, org_id: str, workspace_id: str, kind: str, title: str, message: str, url: Optional[str] = None) -> dict[str, Any]:
    """Deliver one notification through every configured channel."""
    webhook = os.environ.get("CC_ALERT_WEBHOOK_URL", "").strip()
    resend_key = os.environ.get("RESEND_API_KEY", "").strip()
    email_to = [e.strip() for e in os.environ.get("CC_ALERT_EMAIL_TO", "").split(",") if e.strip()]
    sent: dict[str, Any] = {"webhook": None, "email": None}
    if not webhook and not (resend_key and email_to):
        return sent
    payload = {"kind": kind, "title": title, "message": message, "workspace_id": workspace_id, "url": url or os.environ.get("CC_PUBLIC_URL", "")}
    if webhook:
        try:
            r = httpx.post(webhook, json=payload, timeout=5.0)
            sent["webhook"] = r.status_code
            if r.status_code >= 400:
                _audit(store, org_id, "cc.notify.webhook", "failed", f"{r.status_code} {title}")
        except Exception as exc:
            sent["webhook"] = f"{type(exc).__name__}"
            _audit(store, org_id, "cc.notify.webhook", "failed", f"{type(exc).__name__}: {exc} · {title}"[:300])
    if resend_key and email_to:
        try:
            r = httpx.post("https://api.resend.com/emails", timeout=5.0, headers={"Authorization": f"Bearer {resend_key}"},
                           json={"from": os.environ.get("CC_ALERT_EMAIL_FROM", "control-center@resend.dev"), "to": email_to,
                                 "subject": f"[מרכז הבקרה] {title}", "text": f"{message}\n\n{payload['url']}"})
            sent["email"] = r.status_code
            if r.status_code >= 400:
                _audit(store, org_id, "cc.notify.email", "failed", f"{r.status_code} {title}")
        except Exception as exc:
            sent["email"] = f"{type(exc).__name__}"
            _audit(store, org_id, "cc.notify.email", "failed", f"{type(exc).__name__}: {exc} · {title}"[:300])
    return sent
