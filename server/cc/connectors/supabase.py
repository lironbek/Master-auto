"""Supabase connector: projects via the Management API (metadata only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .base import AssetRecord, SyncResult, classify_http_error, make_client

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
