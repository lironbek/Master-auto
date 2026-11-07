"""Project profile ("how is it built") and health scan, built from the
project's assets through their read-only connections.

Profile: per asset, the provider's structural view (repo languages, framework,
dependencies, structure, CI, tests; Vercel setup, env names, domains, last
production deployment; Supabase schema with RLS state). Stored on the asset
(``data.profile``) with a timestamp, and summarised per project.

Scan: deterministic health findings per asset (branch protection, alerts,
committed env files, missing tests/CI/lockfile, failed deploy, plain secrets,
tables without RLS, ...). Stored as a ``project_scans`` row with the findings
list, so scans are comparable over time. A security survey of the live site is
the PT module's job and is linked from the same screen.
"""

from __future__ import annotations

from typing import Any, Optional

from . import connectors
from .connectors import ConnectorError
from .secrets import SecretsUnavailable, decrypt
from .service import active_links, iso, new_id, now

Row = dict[str, Any]
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def _connector_for(store, org_id: str, asset: Row):
    conn = store.get("connections", asset["connection_id"], organization_id=org_id) if asset.get("connection_id") else None
    if not conn or not conn.get("secret_enc"):
        conn = next((c for c in store.list("connections", organization_id=org_id, workspace_id=asset["workspace_id"], provider=asset["provider"])
                     if c.get("secret_enc") and c["status"] != "disconnected"), None)
    if not conn:
        return None, "no live connection for this provider in the workspace"
    try:
        return connectors.build(conn["provider"], decrypt(conn["secret_enc"]), conn.get("config") or {}), ""
    except SecretsUnavailable as exc:
        return None, str(exc)


def profile_asset(store, org_id: str, asset: Row) -> Row:
    """Refresh one asset's profile. Never raises: errors land in profile.error."""
    conn, err = _connector_for(store, org_id, asset)
    prof: dict[str, Any] = {"at": iso(), "error": err}
    if conn:
        try:
            if asset["provider"] == "github" and asset["kind"] == "repo":
                prof.update(conn.repo_profile(asset["name"]))
            elif asset["provider"] == "vercel":
                prof.update(conn.project_profile(asset["external_id"]))
            elif asset["provider"] == "supabase":
                prof.update(conn.project_profile(asset["external_id"]))
            else:
                prof["error"] = "profile not supported for this asset kind"
        except ConnectorError as exc:
            prof["error"] = str(exc)
        except Exception as exc:  # network etc.
            prof["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return store.update("cc_assets", asset["id"], organization_id=org_id, patch={"profile": prof})


def health_asset(conn, asset: Row, prof: dict[str, Any]) -> list[dict[str, Any]]:
    if not conn or prof.get("error"):
        return [{"severity": "info", "title": f"{asset['name']}: לא נסרק", "detail": prof.get("error") or "no connector", "fix": "", "source": asset["provider"]}]
    try:
        if asset["provider"] == "github" and asset["kind"] == "repo":
            return conn.repo_health(asset["name"], prof)
        if asset["provider"] == "vercel":
            return conn.project_health(prof)
        if asset["provider"] == "supabase":
            return conn.project_health(prof)
    except Exception as exc:
        return [{"severity": "info", "title": f"{asset['name']}: הסריקה נכשלה", "detail": f"{type(exc).__name__}: {exc}"[:200], "fix": "", "source": asset["provider"]}]
    return []


def project_assets(store, org_id: str, project_id: str) -> list[Row]:
    return [a for l in active_links(store, org_id, project_id=project_id)
            for a in [store.get("cc_assets", l["asset_id"], organization_id=org_id)] if a and not a.get("removed_at")]


def build_profile(store, org_id: str, project: Row) -> dict[str, Any]:
    assets = [profile_asset(store, org_id, a) for a in project_assets(store, org_id, project["id"])]
    summary = summarize(project, assets)
    store.update("cc_projects", project["id"], organization_id=org_id, patch={"profile_at": iso(), "profile_summary": summary})
    return {"assets": assets, "summary": summary, "at": iso()}


def summarize(project: Row, assets: list[Row]) -> dict[str, Any]:
    """Deterministic architecture summary from the asset profiles."""
    repos = [a for a in assets if a["provider"] == "github"]
    vercels = [a for a in assets if a["provider"] == "vercel"]
    dbs = [a for a in assets if a["provider"] == "supabase"]
    langs: dict[str, int] = {}
    frameworks: list[str] = []
    integrations: list[str] = []
    tests = ci = 0
    for r in repos:
        p = r.get("profile") or {}
        for k, v in (p.get("languages") or {}).items():
            langs[k] = langs.get(k, 0) + int(v)
        if p.get("framework") and p["framework"] not in frameworks:
            frameworks.append(p["framework"])
        for i in p.get("integrations") or []:
            if i not in integrations:
                integrations.append(i)
        tests += bool(p.get("has_tests")); ci += bool(p.get("workflows"))
    total = sum(langs.values()) or 1
    lang_pct = {k: round(100 * v / total) for k, v in sorted(langs.items(), key=lambda kv: -kv[1])[:6]}
    tables = sum(len((d.get("profile") or {}).get("tables") or []) for d in dbs)
    domains = [dm for v in vercels for dm in ((v.get("profile") or {}).get("domains") or [])]
    lines = [f"{project['name']}: {len(repos)} ריפוזיטוריז, {len(vercels)} פריסות Vercel, {len(dbs)} מסדי Supabase ({tables} טבלאות)."]
    if frameworks:
        lines.append("מסגרות: " + ", ".join(frameworks) + ".")
    if lang_pct:
        lines.append("שפות: " + ", ".join(f"{k} {v}%" for k, v in lang_pct.items()) + ".")
    if integrations:
        lines.append("אינטגרציות שזוהו מהתלויות: " + ", ".join(integrations) + ".")
    if repos:
        lines.append(f"בדיקות ב-{tests}/{len(repos)} ריפוזיטוריז, CI ב-{ci}/{len(repos)}.")
    if domains:
        lines.append("כתובות: " + ", ".join(domains[:5]) + ".")
    return {"text": "\n".join(lines), "languages": lang_pct, "frameworks": frameworks, "integrations": integrations,
            "repos": len(repos), "deployments": len(vercels), "databases": len(dbs), "tables": tables, "domains": domains[:10],
            "tests_ratio": f"{tests}/{len(repos)}" if repos else "", "ci_ratio": f"{ci}/{len(repos)}" if repos else ""}


def run_code_scan(store, org_id: str, project: Row, *, actor: str) -> Row:
    """Code review of every repository of the project by Claude (bounded file
    selection, secrets redacted). Needs an Anthropic key: the project's default
    key or ANTHROPIC_API_KEY. Usage is metered to the project's client."""
    from . import codescan
    from .usage import UsageEntryIn, record

    api_key, key_id, model = codescan.resolve_key(store, org_id, project)
    if not api_key:
        raise ConnectorError("no Anthropic key: set the project's default key or ANTHROPIC_API_KEY", status="reauth")
    repos = [a for a in project_assets(store, org_id, project["id"]) if a["provider"] == "github" and a["kind"] == "repo"]
    findings: list[dict[str, Any]] = []
    summaries: list[str] = []
    files_total = 0
    usage_total = {"input": 0, "output": 0}
    errors: list[str] = []
    for a in repos:
        conn, err = _connector_for(store, org_id, a)
        if not conn:
            errors.append(f"{a['name']}: {err}"); continue
        try:
            _, files = codescan.gather(conn, a["name"])
            if not files:
                errors.append(f"{a['name']}: no reviewable source files"); continue
            review, usage = codescan.review_with_claude(api_key, model, a["name"], files)
        except Exception as exc:
            errors.append(f"{a['name']}: {type(exc).__name__}: {exc}"[:200]); continue
        files_total += len(files)
        usage_total["input"] += usage["input"]; usage_total["output"] += usage["output"]
        summaries.append(f"{a['name']}: {review['summary']}")
        findings.extend({**f, "asset_id": a["id"], "asset_name": a["name"]} for f in review["findings"])
    if usage_total["input"] or usage_total["output"]:
        for metric, qty in (("requests", len(summaries)), ("tokens_in", usage_total["input"]), ("tokens_out", usage_total["output"])):
            record(store, org_id, project["workspace_id"],
                   UsageEntryIn(provider="claude", metric=metric, quantity=qty, interface="scan:code", project_id=project["id"], model=model),
                   client_id=project.get("client_id"), source="scan")
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["asset_name"]))
    counts = {k: sum(1 for f in findings if f["severity"] == k) for k in SEVERITY_ORDER}
    grade = "A" if not counts["high"] and not counts["medium"] else ("B" if not counts["high"] else "C")
    row = {"id": new_id("scan"), "organization_id": org_id, "workspace_id": project["workspace_id"], "project_id": project["id"],
           "kind": "code", "status": "completed" if summaries else "failed", "grade": grade if summaries else "", "created_at": iso(), "finished_at": iso(),
           "actor": actor, "findings": findings, "counts": counts, "assets": len(repos), "files": files_total, "model": model, "key_id": key_id,
           "usage": usage_total, "summary": {"text": "\n".join(summaries) or "\n".join(errors), "errors": errors}}
    store.insert("project_scans", row)
    if summaries:
        store.update("cc_projects", project["id"], organization_id=org_id, patch={"last_code_scan_id": row["id"], "last_code_scan_grade": grade, "last_code_scan_at": row["created_at"]})
    return row


def run_scan(store, org_id: str, project: Row, *, actor: str, refresh_profile: bool = True) -> Row:
    """Health scan over all the project's assets; stores and returns the scan row."""
    assets = project_assets(store, org_id, project["id"])
    findings: list[dict[str, Any]] = []
    for a in assets:
        if refresh_profile or not a.get("profile"):
            a = profile_asset(store, org_id, a)
        prof = a.get("profile") or {}
        conn, _ = _connector_for(store, org_id, a)
        for f in health_asset(conn, a, prof):
            findings.append({**f, "asset_id": a["id"], "asset_name": a["name"]})
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["asset_name"]))
    counts = {k: sum(1 for f in findings if f["severity"] == k) for k in SEVERITY_ORDER}
    grade = "A" if not counts["high"] and not counts["medium"] else ("B" if not counts["high"] else "C")
    row = {"id": new_id("scan"), "organization_id": org_id, "workspace_id": project["workspace_id"], "project_id": project["id"],
           "kind": "health", "status": "completed", "grade": grade, "created_at": iso(), "finished_at": iso(), "actor": actor,
           "findings": findings, "counts": counts, "assets": len(assets),
           "summary": summarize(project, [store.get("cc_assets", a["id"], organization_id=org_id) or a for a in assets])}
    store.insert("project_scans", row)
    store.update("cc_projects", project["id"], organization_id=org_id, patch={"last_scan_id": row["id"], "last_scan_grade": grade, "last_scan_at": row["created_at"]})
    return row
