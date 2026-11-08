"""Typed-column map shared by the SQL-backed stores.

Each table has typed key columns used for queries; every other field of the
record is kept in the ``data`` jsonb column (see pt_agent/db/migrations).
"""

from __future__ import annotations

from typing import Any

Row = dict[str, Any]

TYPED: dict[str, set[str]] = {
    "organizations": {"id", "name", "created_at"},
    "users": {"id", "organization_id", "email", "display_name", "created_at"},
    "memberships": {"id", "organization_id", "user_id", "role", "created_at"},
    "sessions": {"id", "organization_id", "user_id", "token_hash", "expires_at", "created_at"},
    "projects": {"id", "organization_id", "name", "description", "created_at"},
    "authorizations": {
        "id", "organization_id", "project_id", "valid_from", "valid_until",
        "control_verified", "created_at",
    },
    "scope_versions": {
        "id", "organization_id", "project_id", "version", "status",
        "authorization_id", "environment", "policy_version", "approved_by",
        "approved_at", "created_at",
    },
    "scan_runs": {
        "id", "organization_id", "project_id", "scope_version_id", "mode",
        "status", "started_at", "stopped_at", "stop_reason", "created_at",
    },
    "actions": {
        "id", "organization_id", "run_id", "scope_version_id", "policy_version",
        "target_host", "module", "risk", "approval_id", "created_at",
    },
    "approvals": {
        "id", "organization_id", "run_id", "action_id", "approver_user_id",
        "target_host", "module", "valid_until", "parameter_fingerprint",
        "revoked", "created_at",
    },
    "findings": {
        "id", "organization_id", "project_id", "run_id", "title", "asset_path",
        "category", "severity", "confidence", "status", "duplicate_of", "created_at",
    },
    "evidence": {
        "id", "organization_id", "project_id", "finding_id", "kind", "sensitivity",
        "redacted_source", "redacted_fingerprint", "checksum",
        "redaction_policy_version", "captured_at", "delete_at", "created_at",
    },
    "report_versions": {
        "id", "organization_id", "project_id", "run_id", "finding_ids",
        "evidence_ids", "created_at",
    },
    "audit_events": {
        "id", "organization_id", "run_id", "actor", "action", "decision",
        "policy_version", "detail", "at",
    },
    "evidence_access_log": {"organization_id", "evidence_id", "actor", "action", "at"},
    # --- Control Center (migration 0003) ---
    "workspaces": {"id", "organization_id", "name", "kind", "created_at"},
    "workspace_members": {"id", "organization_id", "workspace_id", "user_id", "role", "created_at"},
    "cc_projects": {"id", "organization_id", "workspace_id", "name", "owner", "importance", "status", "environment", "created_at"},
    "connections": {"id", "organization_id", "workspace_id", "provider", "account_label", "status", "last_sync_at", "last_attempt_at", "last_error", "created_at"},
    "provider_keys": {"id", "organization_id", "workspace_id", "name", "provider", "account_label", "masked", "scope", "created_at"},
    "cc_assets": {"id", "organization_id", "workspace_id", "connection_id", "external_id", "kind", "name", "provider", "environment", "state", "url", "description", "last_seen_at", "source_updated_at", "removed_at", "created_at"},
    "project_assets": {"id", "organization_id", "project_id", "asset_id", "source", "created_at"},
    "work_sessions": {"id", "organization_id", "workspace_id", "project_id", "title", "goal", "owner", "tool", "status", "external_id", "started_at", "ended_at", "created_at"},
    "activity_events": {"id", "organization_id", "workspace_id", "connection_id", "asset_id", "project_id", "session_id", "external_id", "kind", "result", "environment", "title", "url", "occurred_at", "ingested_at", "created_at"},
    "inbox_items": {"id", "organization_id", "workspace_id", "asset_id", "kind", "status", "suggested_project_id", "reason", "created_at"},
    "cost_entries": {"id", "organization_id", "workspace_id", "project_id", "provider", "kind", "amount", "currency", "period_start", "period_end", "created_at"},
    "cc_agents": {"id", "organization_id", "workspace_id", "project_id", "name", "owner", "provider", "model", "key_id", "enabled", "version", "created_at"},
    "agent_runs": {"id", "organization_id", "workspace_id", "agent_id", "project_id", "session_id", "status", "started_at", "finished_at", "created_at"},
    "alerts": {"id", "organization_id", "workspace_id", "kind", "target_kind", "target_id", "status", "message", "created_at"},
    # --- Usage metering (migration 0006) ---
    "clients": {"id", "organization_id", "workspace_id", "name", "external_ref", "created_at"},
    "usage_entries": {"id", "organization_id", "workspace_id", "project_id", "client_id", "provider", "metric", "quantity", "unit",
                      "interface", "model", "external_id", "occurred_at", "period_start", "created_at"},
    # --- Project profile & health scans (migration 0007) ---
    "project_scans": {"id", "organization_id", "workspace_id", "project_id", "kind", "status", "grade", "created_at", "finished_at"},
    # --- Billing & service module (migration 0008) ---
    "bl_customers": {"id", "organization_id", "workspace_id", "client_id", "name", "email", "phone", "contact_person", "address", "status",
                     "bill_hours", "hourly_rate", "legacy_id", "created_at"},
    "bl_products": {"id", "organization_id", "workspace_id", "project_id", "name", "description", "price", "has_light_user", "light_user_price", "legacy_id", "created_at"},
    "bl_services": {"id", "organization_id", "workspace_id", "description", "price", "recurring", "legacy_id", "created_at"},
    "bl_subscriptions": {"id", "organization_id", "workspace_id", "customer_id", "kind", "product_id", "service_id", "user_count", "light_user_count",
                         "quantity", "valid_from", "valid_until", "legacy_id", "created_at"},
    "bl_employees": {"id", "organization_id", "workspace_id", "user_id", "name", "email", "phone", "position", "role", "hourly_rate", "active", "legacy_id", "created_at"},
    "bl_tickets": {"id", "organization_id", "workspace_id", "number", "customer_id", "product_id", "employee_id", "title", "description", "status", "priority",
                   "contact_person", "contact_phone", "group_name", "image_url", "opened_at", "closed_at", "legacy_id", "created_at"},
    "bl_time_entries": {"id", "organization_id", "workspace_id", "ticket_id", "employee_id", "description", "minutes", "entry_date", "billed_charge_id", "legacy_id", "created_at"},
    "bl_external_updates": {"id", "organization_id", "workspace_id", "ticket_id", "contact_name", "contact_phone", "content", "minutes", "update_date", "legacy_id", "created_at"},
    "bl_charges": {"id", "organization_id", "workspace_id", "customer_id", "period", "status", "subtotal", "vat_pct", "vat", "total", "issued_at", "paid_at", "legacy_id", "created_at"},
    "bl_charge_lines": {"id", "organization_id", "workspace_id", "charge_id", "kind", "ref_id", "description", "quantity", "unit_price", "total", "legacy_id", "created_at"},
    "bl_expenses": {"id", "organization_id", "workspace_id", "name", "amount", "currency", "rate_used", "amount_ils", "category", "expense_date", "description", "recurring", "legacy_id", "created_at"},
    "bl_knowledge": {"id", "organization_id", "workspace_id", "product_id", "title", "content", "category", "legacy_id", "created_at"},
    "bl_fx_rates": {"id", "organization_id", "currency", "rate_date", "rate", "created_at"},
    "bl_settings": {"id", "organization_id", "workspace_id", "created_at"},
}

# Tables that have no `data` column.
NO_DATA_COLUMN = {"audit_events", "evidence_access_log"}

# Tables whose rows may be looked up without an organisation filter
# (authentication bootstrap only).
GLOBAL_LOOKUP_TABLES = {"users", "sessions", "organizations"}

# Timestamp column used for ordering.
ORDER_COLUMN = {"audit_events": "at", "evidence_access_log": "at", "activity_events": "occurred_at", "usage_entries": "occurred_at",
                "bl_tickets": "opened_at", "bl_time_entries": "entry_date", "bl_expenses": "expense_date"}

# Only these tables may be addressed by the generic store API.
ALLOWED_TABLES = set(TYPED)


def split(table: str, row: Row) -> Row:
    """Split a record into typed columns + ``data``."""
    if table not in ALLOWED_TABLES:
        raise ValueError(f"unknown table: {table}")
    typed = TYPED[table]
    out = {k: v for k, v in row.items() if k in typed}
    if table not in NO_DATA_COLUMN:
        out["data"] = {k: v for k, v in row.items() if k not in typed}
    return out


def merge(row: Row) -> Row:
    """Inverse of :func:`split`."""
    data = row.pop("data", None) or {}
    merged = dict(data)
    merged.update(row)
    return merged
