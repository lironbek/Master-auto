"""Seed the control center from an inventory snapshot taken through the
provider consoles/MCPs (GitHub repos, Vercel projects, Supabase projects).

This is the bootstrap for an account that has not connected providers yet:
every item becomes a catalog asset (provider inventory, no connection), items
are grouped into projects by product name, and projects into workspaces by
rule (``comax``/``AnibTech`` -> work workspace, everything else -> personal).
Once a real connection is added and synced, the same external ids are matched
and the rows are taken over by the connection (unique key: workspace, provider,
kind, external_id).

Usage:
  python scripts/seed_inventory.py inventory.json --org ORG_ID --user USER_ID            # emits SQL on stdout
  python scripts/seed_inventory.py inventory.json --org ORG_ID --user USER_ID --dsn $DATABASE_URL   # applies directly
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Only deployment-shaped suffixes are stripped, so product names stay recognisable.
SUFFIXES = ("-api", "-web", "-app", "-site", "-frontend", "-backend", "-db", "-hub")
# Explicit merges for names that differ in spelling but are one product.
ALIASES = {"7015": "gdud7015", "vehicle-7015": "gdud7015", "sik-sak": "siksak", "goldenberg-crm": "goldenberg",
           "shlomit-folio": "shlomit", "comaxtr": "comax-translate"}
WORK_MARKERS = ("comax", "anibtech", "combox", "comaxtr", "planogrma", "excel-reorder", "comax-imports")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def nid(prefix: str, *key: str) -> str:
    """Deterministic id when a stable key is given, so re-running the seed is a no-op."""
    if key:
        return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, 'control-center/' + '/'.join(key)).hex[:16]}"
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def product_key(name: str) -> str:
    n = name.lower()
    n = n.split("/")[-1]
    n = re.sub(r"[_\s]+", "-", n)
    n = re.sub(r"-[0-9a-f]{8}$", "", n)
    changed = True
    while changed:
        changed = False
        for s in SUFFIXES:
            if n.endswith(s) and len(n) > len(s) + 1:
                n = n[: -len(s)]; changed = True
    n = ALIASES.get(n, n)
    return n


def canonical(keys: list[str], key: str) -> str:
    """Merge a key into an existing two-token prefix (emunah-harmony-system ->
    emunah-harmony) or a hyphen-insensitive twin (sik-sak == siksak)."""
    flat = key.replace("-", "")
    for k in keys:
        if k.replace("-", "") == flat:
            return k
    for k in keys:
        if "-" in k and key.startswith(k + "-"):
            return k
    for k in keys:
        if "-" in key and k.startswith(key + "-"):
            return key
    return key


def is_work(name: str, owner: str = "") -> bool:
    n = f"{owner}/{name}".lower()
    return any(m in n for m in WORK_MARKERS)


def q(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def build(inv: dict, org: str, user: str, *, compact: bool = False) -> tuple[list[str], dict]:
    sql: list[str] = []
    ws = {
        "work": {"id": nid("ws", org, "work"), "name": "קומקס", "kind": "work"},
        "personal": {"id": nid("ws", org, "personal"), "name": "פרויקטים פרטיים", "kind": "personal"},
    }
    for w in ws.values():
        sql.append(f"insert into workspaces (id, organization_id, name, kind, created_at, data) values ({q(w['id'])}, {q(org)}, {q(w['name'])}, {q(w['kind'])}, now(), '{{}}'::jsonb) on conflict do nothing;")
        sql.append(f"insert into workspace_members (id, organization_id, workspace_id, user_id, role, created_at, data) values ({q(nid('wsm', w['id'], user))}, {q(org)}, {q(w['id'])}, {q(user)}, 'admin', now(), '{{}}'::jsonb) on conflict do nothing;")

    projects: dict[tuple[str, str], dict] = {}
    assets: list[dict] = []
    stats = {"repos": 0, "vercel": 0, "supabase": 0, "projects": 0}

    def project_for(name: str, owner: str = "") -> dict:
        ws_key = "work" if is_work(name, owner) else "personal"
        existing = [k[1] for k in projects if k[0] == ws_key]
        key = (ws_key, canonical(existing, product_key(name)))
        if key not in projects:
            projects[key] = {"id": nid("prj", ws[key[0]]["id"], key[1]), "workspace_id": ws[key[0]]["id"], "name": key[1], "owner": "", "importance": "normal",
                             "status": "active", "environment": "unclassified"}
        return projects[key]

    ordered = sorted(
        [("github", r) for r in inv.get("github", [])] + [("vercel", v) for v in inv.get("vercel", [])] + [("supabase", s) for s in inv.get("supabase", [])],
        key=lambda kv: len(product_key(kv[1].get("full_name", kv[1].get("name", "")).split("/")[-1])),
    )
    for kind, r in ordered:
      if kind == "github":
        owner, name = r["full_name"].split("/", 1)
        p = project_for(name, owner)
        assets.append({"id": nid("ast", p["workspace_id"], "github", "repo", r["full_name"]), "workspace_id": p["workspace_id"], "project_id": p["id"], "external_id": r["full_name"],
                       "kind": "repo", "name": r["full_name"], "provider": "github", "environment": "development",
                       "state": r.get("visibility", ""), "url": r.get("url", ""), "source_updated_at": r.get("pushed_at"),
                       "description": "", "meta": {"seeded_from": "inventory", "owner": owner}})
        stats["repos"] += 1
      elif kind == "vercel":
        v = r
        p = project_for(v["name"])
        env = "production"
        assets.append({"id": nid("ast", p["workspace_id"], "vercel", "vercel_project", v["id"]), "workspace_id": p["workspace_id"], "project_id": p["id"], "external_id": v["id"],
                       "kind": "vercel_project", "name": v["name"], "provider": "vercel", "environment": env, "state": "project",
                       "url": f"https://vercel.com/{inv.get('vercel_team_slug', '')}/{v['name']}",
                       "source_updated_at": datetime.fromtimestamp(v["updatedAt"] / 1000, tz=timezone.utc).isoformat() if v.get("updatedAt") else None,
                       "description": "", "meta": {"seeded_from": "inventory"}})
        stats["vercel"] += 1
      else:
        s = r
        p = project_for(s["name"])
        assets.append({"id": nid("ast", p["workspace_id"], "supabase", "supabase_project", s["id"]), "workspace_id": p["workspace_id"], "project_id": p["id"], "external_id": s["id"],
                       "kind": "supabase_project", "name": s["name"], "provider": "supabase", "environment": "production",
                       "state": s.get("status", ""), "url": f"https://supabase.com/dashboard/project/{s['id']}",
                       "source_updated_at": s.get("created_at"), "description": "מסד הנתונים של הפרויקט",
                       "meta": {"seeded_from": "inventory", "region": s.get("region", "")}})
        stats["supabase"] += 1

    if compact:
        rows = ", ".join(f"({q(p['id'])}, {q(org)}, {q(p['workspace_id'])}, {q(p['name'])}, '', 'normal', 'active', 'unclassified', now(), {q({'description': '', 'seeded_from': 'inventory'})})" for p in projects.values())
        stats["projects"] = len(projects)
        sql.append(f"insert into cc_projects (id, organization_id, workspace_id, name, owner, importance, status, environment, created_at, data) values {rows} on conflict do nothing;")
        arows = ", ".join(f"({q(a['id'])}, {q(org)}, {q(a['workspace_id'])}, null, {q(a['external_id'])}, {q(a['kind'])}, {q(a['name'])}, {q(a['provider'])}, {q(a['environment'])}, {q(a['state'])}, {q(a['url'])}, {q(a['description'])}, now(), {q(a['source_updated_at'])}, now(), {q({'meta': a['meta']})})" for a in assets)
        sql.append(f"insert into cc_assets (id, organization_id, workspace_id, connection_id, external_id, kind, name, provider, environment, state, url, description, last_seen_at, source_updated_at, created_at, data) values {arows} on conflict (workspace_id, provider, kind, external_id) do nothing;")
        lrows = ", ".join(f"({q(nid('pa', a['project_id'], a['id']))}, {q(org)}, {q(a['project_id'])}, {q(a['id'])}, 'auto', now(), '{{}}'::jsonb)" for a in assets)
        sql.append(f"insert into project_assets (id, organization_id, project_id, asset_id, source, created_at, data) values {lrows} on conflict do nothing;")
        sql.append(f"insert into audit_events (id, organization_id, actor, action, decision, policy_version, detail, at) values ({q(nid('aud'))}, {q(org)}, 'seed', 'cc.seed.inventory', 'ok', '', {q(json.dumps(stats))}, now());")
        return sql, stats
    for p in projects.values():
        stats["projects"] += 1
        sql.append(f"insert into cc_projects (id, organization_id, workspace_id, name, owner, importance, status, environment, created_at, data) values ({q(p['id'])}, {q(org)}, {q(p['workspace_id'])}, {q(p['name'])}, '', 'normal', 'active', 'unclassified', now(), {q({'description': '', 'seeded_from': 'inventory'})}) on conflict do nothing;")
    for a in assets:
        sql.append(f"insert into cc_assets (id, organization_id, workspace_id, connection_id, external_id, kind, name, provider, environment, state, url, description, last_seen_at, source_updated_at, created_at, data) values ({q(a['id'])}, {q(org)}, {q(a['workspace_id'])}, null, {q(a['external_id'])}, {q(a['kind'])}, {q(a['name'])}, {q(a['provider'])}, {q(a['environment'])}, {q(a['state'])}, {q(a['url'])}, {q(a['description'])}, now(), {q(a['source_updated_at'])}, now(), {q({'meta': a['meta']})}) on conflict (workspace_id, provider, kind, external_id) do nothing;")
        sql.append(f"insert into project_assets (id, organization_id, project_id, asset_id, source, created_at, data) select {q(nid('pa', a['project_id'], a['id']))}, {q(org)}, {q(a['project_id'])}, id, 'auto', now(), '{{}}'::jsonb from cc_assets where workspace_id = {q(a['workspace_id'])} and provider = {q(a['provider'])} and kind = {q(a['kind'])} and external_id = {q(a['external_id'])} on conflict do nothing;")
    sql.append(f"insert into audit_events (id, organization_id, actor, action, decision, policy_version, detail, at) values ({q(nid('aud'))}, {q(org)}, 'seed', 'cc.seed.inventory', 'ok', '', {q(json.dumps(stats))}, now());")
    return sql, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inventory")
    ap.add_argument("--org", required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--dsn", default="")
    ap.add_argument("--compact", action="store_true", help="one multi-row insert per table")
    args = ap.parse_args()
    inv = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    sql, stats = build(inv, args.org, args.user, compact=args.compact)
    if args.dsn:
        import psycopg
        with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
            for stmt in sql:
                cur.execute(stmt)
            conn.commit()
        print("seeded:", stats, file=sys.stderr)
    else:
        print("\n".join(sql))
        print("-- stats:", json.dumps(stats), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
