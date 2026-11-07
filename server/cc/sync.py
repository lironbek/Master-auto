"""Sync engine (PRD section 4 "תהליך חיבור ושיוך", section 6 "קליטה").

- Identity: an asset is (workspace, provider, kind, external_id); an event is
  (workspace, connection, external_id). Re-ingestion updates the same row.
  A catalog row seeded from an inventory snapshot (no connection) is taken
  over by the first connection that reports the same identity, or the same
  provider/kind/name when the snapshot had no stable id.
- Ordering: a late event updates the snapshot only if newer by source time.
- Assignment: manual assignment wins and is kept; automatic suggestions use
  stable links (e.g. a Vercel project linked to an already-assigned repo).
- Disappearance: an asset missing from a *full* sync with unchanged scope is
  marked removed; a partial sync leaves the last known state with a label.
- Alerts: production failure on an assigned asset, repeated failures, sync
  delay, permission loss. An alert that was acknowledged or snoozed is not
  re-opened by the same event.
- Failure modes: a provider refusal sets reauth/rate_limited; a network or
  store error sets 'error' (retried by the scheduler); 'disconnected' is only
  ever set by a user.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from . import connectors
from .connectors import ConnectorError, SyncResult
from .secrets import SecretsUnavailable, decrypt
from .service import assignment_index, iso, new_id, now, parse_dt

Row = dict[str, Any]

STALE_AFTER = timedelta(minutes=45)   # PRD section 5 "טריות"
# Statuses for which "no recent successful sync" is worth an alert.
WATCHED = ("ok", "partial", "error", "rate_limited")


def run_connection_sync(store, org_id: str, connection: Row, *, actor: str = "system") -> dict[str, Any]:
    """Synchronise one connection. Returns a summary; never raises on provider
    or store failure (the connection status carries the outcome)."""
    ws = connection["workspace_id"]
    summary = {"assets": 0, "events": 0, "new_inbox": 0, "removed": 0, "status": "ok", "notes": []}
    store.update("connections", connection["id"], organization_id=org_id, patch={"last_attempt_at": iso()})

    try:
        secret = decrypt(connection.get("secret_enc", ""))
    except SecretsUnavailable as exc:
        return _fail(store, org_id, connection, "reauth", str(exc), summary)

    try:
        conn = connectors.build(connection["provider"], secret, connection.get("config") or {})
        result: SyncResult = conn.sync(since=parse_dt(connection.get("last_sync_at")))
    except ConnectorError as exc:
        return _fail(store, org_id, connection, exc.status, str(exc), summary)
    except Exception as exc:  # network etc. — transient, keep retrying
        return _fail(store, org_id, connection, "error", f"{type(exc).__name__}: {exc}"[:300], summary)

    try:
        _ingest(store, org_id, connection, result, summary)
    except Exception as exc:  # store/db error: never leave the cron loop half-done
        return _fail(store, org_id, connection, "error", f"ingest: {type(exc).__name__}: {exc}"[:300], summary)

    status = "partial" if result.partial else "ok"
    store.update("connections", connection["id"], organization_id=org_id, patch={
        "status": status, "last_sync_at": iso(), "last_error": "", "coverage": result.coverage,
        "capabilities": list(result.coverage), "notes": result.notes,
    })
    summary["status"] = status
    summary["notes"] = result.notes
    return summary


def _ingest(store, org_id: str, connection: Row, result: SyncResult, summary: dict) -> None:
    ws, provider, cid = connection["workspace_id"], connection["provider"], connection["id"]

    # Every catalog row of this provider in the workspace, whoever reported it:
    # the unique key is (workspace, provider, kind, external_id), so an insert
    # must never race a row owned by another (or no) connection.
    all_rows = store.list("cc_assets", organization_id=org_id, workspace_id=ws, provider=provider)
    by_identity = {(a["kind"], a["external_id"]): a for a in all_rows}
    by_name = {(a["kind"], a["name"].lower()): a for a in all_rows if not a.get("connection_id")}
    mine = {a["external_id"]: a for a in all_rows if a.get("connection_id") == cid}
    seen: set[str] = set()
    ext_to_asset_id: dict[str, str] = {}

    # --- assets -----------------------------------------------------------
    for rec in result.assets:
        seen.add(rec.external_id)
        patch = {
            "kind": rec.kind, "name": rec.name, "provider": provider, "environment": rec.environment,
            "state": rec.state, "url": rec.url, "last_seen_at": iso(), "source_updated_at": rec.source_updated_at,
            "removed_at": None, "meta": rec.meta, "connection_id": cid,
        }
        cur = by_identity.get((rec.kind, rec.external_id)) or by_name.get((rec.kind, rec.name.lower()))
        if cur:
            # Take-over of a seeded/unowned row keeps its id and assignments; a
            # name-matched row also learns the provider's stable id.
            patch["external_id"] = rec.external_id
            # Manual description wins over provider description (PRD 4.4).
            if not cur.get("description_manual"):
                patch["description"] = rec.description
            row = store.update("cc_assets", cur["id"], organization_id=org_id, patch=patch)
        else:
            row = store.insert("cc_assets", {"id": new_id("ast"), "organization_id": org_id, "workspace_id": ws,
                                          "external_id": rec.external_id, "description": rec.description,
                                          "created_at": iso(), **patch})
            _maybe_inbox(store, org_id, ws, row, summary)
        ext_to_asset_id[rec.external_id] = row["id"]
        summary["assets"] += 1

    # Disappearance only on a full sync with unchanged scope (PRD 4.5), and only
    # for rows this connection reported before.
    if not result.partial:
        for ext, cur in mine.items():
            if ext not in seen and not cur.get("removed_at"):
                store.update("cc_assets", cur["id"], organization_id=org_id, patch={"removed_at": iso(), "state": "removed_at_source"})
                _inbox(store, org_id, ws, cur["id"], "missing_source", "נעלם בסנכרון מלא עם אותו היקף הרשאה", summary)
                summary["removed"] += 1

    # --- events -----------------------------------------------------------
    assigned = assignment_index(store, org_id)
    for ev in result.events:
        asset_id = ext_to_asset_id.get(ev.asset_external_id) or (mine.get(ev.asset_external_id) or {}).get("id")
        project_id = assigned.get(asset_id) if asset_id else None
        key_rows = store.list("activity_events", organization_id=org_id, workspace_id=ws, connection_id=cid, external_id=ev.external_id)
        row = {
            "asset_id": asset_id, "project_id": project_id, "kind": ev.kind, "result": ev.result, "environment": ev.environment,
            "title": ev.title, "url": ev.url, "occurred_at": ev.occurred_at, "ingested_at": iso(), "meta": ev.meta,
        }
        changed = True
        if key_rows:
            cur = key_rows[0]
            old_t, new_t = parse_dt(cur.get("occurred_at")), parse_dt(ev.occurred_at)
            if old_t and new_t and new_t < old_t:
                continue  # late, older snapshot: keep history, don't regress (PRD 6)
            # News = the result changed, or the asset has since been assigned to a
            # project (the failure now has an owner to alert).
            changed = cur.get("result") != ev.result or bool(project_id and not cur.get("project_id"))
            # keep an explicit session link made by a user
            row.pop("project_id", None) if cur.get("session_id") else None
            store.update("activity_events", cur["id"], organization_id=org_id, patch=row)
        else:
            store.insert("activity_events", {"id": new_id("evt"), "organization_id": org_id, "workspace_id": ws,
                                             "connection_id": cid, "external_id": ev.external_id,
                                             "created_at": iso(), **row})
        summary["events"] += 1
        # Alert only when the failure is news: a re-ingested old failure must not
        # re-open an alert the user already acknowledged.
        if changed and ev.result == "failure" and project_id and ev.environment == "production":
            _alert(store, org_id, ws, "failure", "asset", asset_id or "", f"כשל בייצור: {ev.title}"[:200],
                   occurred_at=ev.occurred_at)


def _fail(store, org_id, connection, status, message, summary):
    store.update("connections", connection["id"], organization_id=org_id, patch={"status": status, "last_error": message[:300]})
    if status == "reauth":
        _alert(store, org_id, connection["workspace_id"], "permission", "connection", connection["id"],
               f"{connection['provider']}: {message}"[:200], occurred_at=iso())
    summary["status"] = status
    summary["notes"] = [message]
    return summary


def _maybe_inbox(store, org_id, ws, asset: Row, summary) -> None:
    """New asset: suggest a project from a stable link, else queue for triage."""
    suggestion = None
    meta = asset.get("meta") or {}
    if asset["provider"] == "vercel" and meta.get("linked_repo"):
        # A Vercel project linked to a repo that is already assigned.
        for repo in store.list("cc_assets", organization_id=org_id, workspace_id=ws, provider="github", kind="repo"):
            if repo["name"].lower() == meta["linked_repo"].lower():
                pid = assignment_index(store, org_id).get(repo["id"])
                if pid:
                    suggestion = pid
                break
    _inbox(store, org_id, ws, asset["id"], "new_asset",
           "מוצע לפי קישור רשמי לריפוזיטורי משויך" if suggestion else "נכס חדש מהסנכרון", summary, suggestion)


def _inbox(store, org_id, ws, asset_id, kind, reason, summary, suggested=None) -> None:
    opened = store.list("inbox_items", organization_id=org_id, workspace_id=ws, asset_id=asset_id, status="open")
    if any(i["kind"] == kind for i in opened):
        return
    store.insert("inbox_items", {"id": new_id("inb"), "organization_id": org_id, "workspace_id": ws, "asset_id": asset_id,
                                 "kind": kind, "status": "open", "suggested_project_id": suggested, "reason": reason, "created_at": iso()})
    summary["new_inbox"] += 1


def _alert(store, org_id, ws, kind, target_kind, target_id, message, *, occurred_at: Optional[str] = None) -> None:
    """Open an alert unless one for the same target/kind is already open, or was
    acknowledged/snoozed after the triggering event happened."""
    existing = store.list("alerts", organization_id=org_id, workspace_id=ws, target_id=target_id, kind=kind)
    when = parse_dt(occurred_at)
    for a in existing:
        if a["status"] == "open":
            return
        if a["status"] in ("acknowledged", "snoozed"):
            acted = parse_dt(a.get("created_at"))
            if when is None or acted is None or acted >= when:
                return
    store.insert("alerts", {"id": new_id("alr"), "organization_id": org_id, "workspace_id": ws, "kind": kind,
                            "target_kind": target_kind, "target_id": target_id, "status": "open", "message": message, "created_at": iso()})


def freshness(connection: Row) -> dict[str, Any]:
    """PRD section 5: last successful sync and last event shown separately."""
    last = parse_dt(connection.get("last_sync_at"))
    stale = (last is None) or (now() - last > STALE_AFTER)
    return {"last_sync_at": connection.get("last_sync_at"), "stale": stale}


def check_sync_delays(store, org_id: str, workspace_ids: list[str]) -> int:
    n = 0
    for ws in workspace_ids:
        for c in store.list("connections", organization_id=org_id, workspace_id=ws):
            if c["status"] in WATCHED and freshness(c)["stale"]:
                _alert(store, org_id, ws, "sync_delay", "connection", c["id"], f"{c['provider']}: אין סנכרון תקין מעל 45 דקות",
                       occurred_at=c.get("last_sync_at") or c.get("created_at"))
                n += 1
    return n
