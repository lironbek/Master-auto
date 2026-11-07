"""Storage abstraction.

The API talks to a ``Store``; the implementation is chosen from the
environment (``get_store``). Every read is scoped by ``organization_id`` so an
id in a URL path never bypasses the ownership check (PRD section 17,
acceptance criterion 2). The one exception is ``find_one`` on the
authentication tables, used to resolve a session token or an email to its
organisation.
"""

from __future__ import annotations

import os
from typing import Any, Optional, Protocol

from .columns import GLOBAL_LOOKUP_TABLES, ORDER_COLUMN, Row


class Store(Protocol):
    def insert(self, table: str, row: Row) -> Row: ...
    def get(self, table: str, row_id: str, *, organization_id: str) -> Optional[Row]: ...
    def update(self, table: str, row_id: str, *, organization_id: str, patch: Row) -> Optional[Row]: ...
    def list(self, table: str, *, organization_id: str, **filters: Any) -> list[Row]: ...
    def find_one(self, table: str, **filters: Any) -> Optional[Row]: ...
    def list_organization_ids(self) -> list[str]: ...


class MemoryStore:
    """In-process store used for tests, local runs, and as a fallback when no
    database is configured."""

    def __init__(self) -> None:
        self._tables: dict[str, dict[str, Row]] = {}
        self._seq = 0

    def _t(self, table: str) -> dict[str, Row]:
        return self._tables.setdefault(table, {})

    def insert(self, table: str, row: Row) -> Row:
        row = dict(row)
        if "id" not in row:
            self._seq += 1
            row["id"] = self._seq
        self._t(table)[row["id"]] = row
        return dict(row)

    def get(self, table: str, row_id: str, *, organization_id: str) -> Optional[Row]:
        row = self._t(table).get(row_id)
        if row is None or row.get("organization_id") != organization_id:
            return None
        return dict(row)

    def update(self, table: str, row_id: str, *, organization_id: str, patch: Row) -> Optional[Row]:
        row = self._t(table).get(row_id)
        if row is None or row.get("organization_id") != organization_id:
            return None
        row.update(patch)
        return dict(row)

    def list(self, table: str, *, organization_id: str, **filters: Any) -> list[Row]:
        key = ORDER_COLUMN.get(table, "created_at")
        out = []
        for row in self._t(table).values():
            if row.get("organization_id") != organization_id:
                continue
            if all(row.get(k) == v for k, v in filters.items()):
                out.append(dict(row))
        out.sort(key=lambda r: str(r.get(key, "")))
        return out

    def find_one(self, table: str, **filters: Any) -> Optional[Row]:
        if table not in GLOBAL_LOOKUP_TABLES:
            raise ValueError(f"find_one not permitted on {table}")
        for row in self._t(table).values():
            if all(row.get(k) == v for k, v in filters.items()):
                return dict(row)
        return None

    def list_organization_ids(self) -> list[str]:
        """Every organisation id (scheduler / unauthenticated reporter lookups)."""
        return [r["id"] for r in self._t("organizations").values()]


_store: Optional[Store] = None


def postgres_dsn() -> str:
    for key in ("DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    return ""


def backend_name() -> str:
    if postgres_dsn():
        return "postgres"
    if os.environ.get("SUPABASE_URL", "").strip() and os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip():
        return "supabase"
    return "memory"


def get_store() -> Store:
    """Return the process-wide store.

    Selection order: Postgres (``DATABASE_URL`` / ``POSTGRES_URL``, e.g. Neon
    via Vercel) > Supabase (``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``)
    > in-memory fallback.
    """
    global _store
    if _store is not None:
        return _store
    name = backend_name()
    if name == "postgres":
        from .postgres import PostgresStore

        _store = PostgresStore(postgres_dsn())
    elif name == "supabase":
        from .supabase import SupabaseStore

        _store = SupabaseStore(
            os.environ["SUPABASE_URL"].strip(), os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
        )
    else:
        _store = MemoryStore()
    return _store


def reset_store_for_tests() -> None:
    global _store
    _store = None
