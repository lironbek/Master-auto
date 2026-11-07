"""Supabase connector: projects via the Management API (metadata only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .base import AssetRecord, ConnectorError, SyncResult, classify_http_error, make_client

API = "https://api.supabase.com"


class SupabaseConnector:
    provider = "supabase"

    def __init__(self, token: str):
        self.token = token

    def _client(self):
        return make_client({"Authorization": f"Bearer {self.token}"})

    def verify(self) -> dict[str, Any]:
        with self._client() as c:
            r = c.get(f"{API}/v1/organizations")
            if r.status_code >= 400:
                raise classify_http_error(r)
            orgs = r.json()
            return {"account": ", ".join(o.get("name", "") for o in orgs)[:120], "capabilities": ["inventory"]}

    # --- destructive actions (explicit capability, never part of sync) --------

    def pause_project(self, ref: str) -> dict[str, Any]:
        with self._client() as c:
            r = c.post(f"{API}/v1/projects/{ref}/pause")
            if r.status_code in (401, 403, 404):
                raise ConnectorError("the Supabase token cannot pause this project", status="reauth")
            if r.status_code >= 400:
                raise classify_http_error(r)
            return {"paused": True}

    def delete_project(self, ref: str) -> dict[str, Any]:
        with self._client() as c:
            r = c.delete(f"{API}/v1/projects/{ref}")
            if r.status_code in (401, 403, 404):
                raise ConnectorError("the Supabase token cannot delete this project", status="reauth")
            if r.status_code >= 400:
                raise classify_http_error(r)
            return {"deleted": True}

    def project_profile(self, ref: str) -> dict[str, Any]:
        """Database shape: tables (public schema) with row estimates, RLS state,
        extensions, Postgres version. Schema only, never row contents."""
        out: dict[str, Any] = {"ref": ref}
        with self._client() as c:
            r = c.get(f"{API}/v1/projects/{ref}")
            if r.status_code >= 400:
                raise classify_http_error(r)
            p = r.json()
            out.update({"name": p.get("name"), "region": p.get("region"), "status": p.get("status"), "postgres_version": (p.get("database") or {}).get("version", "")})
            q = ("select c.relname as table_name, c.relrowsecurity as rls, coalesce(s.n_live_tup,0) as rows "
                 "from pg_class c join pg_namespace n on n.oid=c.relnamespace left join pg_stat_user_tables s on s.relid=c.oid "
                 "where n.nspname='public' and c.relkind='r' order by 1")
            r = c.post(f"{API}/v1/projects/{ref}/database/query", json={"query": q})
            out["tables"] = [{"name": t["table_name"], "rls": bool(t["rls"]), "rows": int(t["rows"])} for t in r.json()] if r.status_code < 400 and isinstance(r.json(), list) else []
            out["tables_error"] = "" if r.status_code < 400 else f"{r.status_code}"
            r = c.post(f"{API}/v1/projects/{ref}/database/query", json={"query": "select count(*) as n from pg_policies where schemaname='public'"})
            out["policies"] = int(r.json()[0]["n"]) if r.status_code < 400 and isinstance(r.json(), list) and r.json() else None
        return out

    def project_health(self, profile: dict[str, Any]) -> list[dict[str, Any]]:
        f: list[dict[str, Any]] = []

        def add(sev, title, detail, fix=""):
            f.append({"severity": sev, "title": title, "detail": detail, "fix": fix, "source": "supabase"})

        if profile.get("status") not in ("ACTIVE_HEALTHY", None):
            add("high", "הפרויקט אינו תקין", str(profile.get("status")), "בדוק ב-Supabase dashboard.")
        no_rls = [t["name"] for t in profile.get("tables", []) if not t["rls"]]
        if no_rls:
            add("high" if len(no_rls) > 3 else "medium", f"{len(no_rls)} טבלאות ללא RLS", ", ".join(no_rls[:15]), "הפעל RLS והגדר policies, או ודא שרק service role ניגש.")
        if profile.get("tables") and profile.get("policies") == 0 and not no_rls:
            add("info", "RLS מופעל ללא policies", "גישה רק דרך service role / בעל הטבלאות.")
        if profile.get("tables_error"):
            add("info", "לא ניתן לקרוא את הסכימה", f"Management API החזיר {profile['tables_error']}.")
        return f

    def sync(self, *, since: Optional[datetime] = None) -> SyncResult:
        res = SyncResult(coverage={"inventory": "full"}, notes=["Supabase exposes infrastructure status only; app health is separate."])
        with self._client() as c:
            r = c.get(f"{API}/v1/projects")
            if r.status_code >= 400:
                raise classify_http_error(r)
            for p in r.json():
                res.assets.append(AssetRecord(
                    external_id=p.get("id") or p.get("ref"), kind="supabase_project", name=p.get("name", ""),
                    environment="production", state=p.get("status", ""),
                    url=f"https://supabase.com/dashboard/project/{p.get('id') or p.get('ref')}",
                    source_updated_at=p.get("created_at"),
                    meta={"region": p.get("region", ""), "organization_id": p.get("organization_id", "")},
                ))
        return res
