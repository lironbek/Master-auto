"""Supabase (PostgREST) store.

A thin client over the REST endpoint so no heavy SDK is needed in the
serverless bundle. Rows are written with typed key columns plus the full
record in ``data`` (see db/migrations/0001_init.sql).
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from .columns import Row

from .columns import GLOBAL_LOOKUP_TABLES  # noqa: E402
from .columns import merge as _merge, split as _split  # noqa: E402


class SupabaseStore:
    def __init__(self, url: str, service_role_key: str, *, timeout: float = 10.0):
        self._base = url.rstrip("/") + "/rest/v1"
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._client = httpx.Client(timeout=timeout)

    # -- helpers -----------------------------------------------------------
    def _req(self, method: str, table: str, *, params: Optional[dict] = None,
             body: Any = None, prefer: str = "") -> list[Row]:
        headers = dict(self._headers)
        if prefer:
            headers["Prefer"] = prefer
        r = self._client.request(
            method, f"{self._base}/{table}", params=params, headers=headers,
            content=json.dumps(body, default=str) if body is not None else None,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"supabase {method} {table}: {r.status_code} {r.text[:300]}")
        if not r.content:
            return []
        out = r.json()
        return out if isinstance(out, list) else [out]

    # -- Store protocol ----------------------------------------------------
    def insert(self, table: str, row: Row) -> Row:
        rows = self._req("POST", table, body=_split(table, row), prefer="return=representation")
        return _merge(rows[0]) if rows else dict(row)

    def get(self, table: str, row_id: str, *, organization_id: str) -> Optional[Row]:
        rows = self._req(
            "GET", table,
            params={"id": f"eq.{row_id}", "organization_id": f"eq.{organization_id}", "limit": "1"},
        )
        return _merge(rows[0]) if rows else None

    def update(self, table: str, row_id: str, *, organization_id: str, patch: Row) -> Optional[Row]:
        current = self.get(table, row_id, organization_id=organization_id)
        if current is None:
            return None
        current.update(patch)
        rows = self._req(
            "PATCH", table,
            params={"id": f"eq.{row_id}", "organization_id": f"eq.{organization_id}"},
            body=_split(table, current), prefer="return=representation",
        )
        return _merge(rows[0]) if rows else current

    def list(self, table: str, *, organization_id: str, **filters: Any) -> list[Row]:
        params = {"organization_id": f"eq.{organization_id}"}
        for k, v in filters.items():
            params[k] = f"eq.{v}"
        return [_merge(r) for r in self._req("GET", table, params=params)]

    def find_one(self, table: str, **filters: Any) -> Optional[Row]:
        if table not in GLOBAL_LOOKUP_TABLES:
            raise ValueError(f"find_one not permitted on {table}")
        params = {k: f"eq.{v}" for k, v in filters.items()}
        params["limit"] = "1"
        rows = self._req("GET", table, params=params)
        return _merge(rows[0]) if rows else None

    def list_organization_ids(self) -> list[str]:
        rows = self._req("GET", "organizations", params={"select": "id", "order": "created_at"})
        return [r["id"] for r in rows]
