"""Postgres store (Neon via Vercel, or any Postgres).

Uses psycopg 3 with a lazily opened, reused connection. Serverless cold
starts open one connection; a dropped connection is reopened on the next call.
Table names are validated against the schema allowlist and quoted as
identifiers, never interpolated as text.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .columns import ALLOWED_TABLES, GLOBAL_LOOKUP_TABLES, NO_DATA_COLUMN, ORDER_COLUMN, Row, merge, split


def _jsonable(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _normalize(row: Row) -> Row:
    """Make DB rows JSON-friendly (datetimes -> ISO strings)."""
    return {k: _jsonable(v) for k, v in row.items()}


def _bind(cols: Row) -> Row:
    """Wrap list/dict values (jsonb columns such as data, finding_ids) for psycopg."""
    out = {}
    for k, v in cols.items():
        if isinstance(v, (list, dict)):
            out[k] = Jsonb(json.loads(json.dumps(v, default=str)))
        else:
            out[k] = v
    return out


class PostgresStore:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn: Optional[psycopg.Connection] = None

    # -- connection --------------------------------------------------------
    def _c(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._dsn, autocommit=True, row_factory=dict_row)
        return self._conn

    def _run(self, q, params, *, fetch: str):
        """Execute with one reconnect: a pooler closes idle connections without the
        client noticing until the next statement fails."""
        for attempt in (0, 1):
            try:
                with self._c().cursor() as cur:
                    cur.execute(q, params)
                    return cur.fetchone() if fetch == "one" else cur.fetchall()
            except (psycopg.OperationalError, psycopg.InterfaceError):
                if attempt:
                    raise
                try:
                    if self._conn is not None:
                        self._conn.close()
                finally:
                    self._conn = None

    def _table(self, table: str) -> sql.Identifier:
        if table not in ALLOWED_TABLES:
            raise ValueError(f"unknown table: {table}")
        return sql.Identifier(table)

    # -- Store protocol ----------------------------------------------------
    def insert(self, table: str, row: Row) -> Row:
        cols = _bind(split(table, row))
        names = list(cols)
        q = sql.SQL("insert into {t} ({cols}) values ({vals}) returning *").format(
            t=self._table(table),
            cols=sql.SQL(", ").join(map(sql.Identifier, names)),
            vals=sql.SQL(", ").join(sql.Placeholder() * len(names)),
        )
        got = self._run(q, [cols[n] for n in names], fetch="one")
        return merge(_normalize(dict(got))) if got else dict(row)

    def get(self, table: str, row_id: str, *, organization_id: str) -> Optional[Row]:
        q = sql.SQL("select * from {t} where id = %s and organization_id = %s limit 1").format(
            t=self._table(table)
        )
        got = self._run(q, [row_id, organization_id], fetch="one")
        return merge(_normalize(dict(got))) if got else None

    def update(self, table: str, row_id: str, *, organization_id: str, patch: Row) -> Optional[Row]:
        current = self.get(table, row_id, organization_id=organization_id)
        if current is None:
            return None
        current.update(patch)
        cols = split(table, current)
        cols.pop("id", None)
        cols.pop("organization_id", None)
        cols = _bind(cols)
        names = list(cols)
        q = sql.SQL("update {t} set {sets} where id = %s and organization_id = %s returning *").format(
            t=self._table(table),
            sets=sql.SQL(", ").join(
                sql.SQL("{} = %s").format(sql.Identifier(n)) for n in names
            ),
        )
        got = self._run(q, [cols[n] for n in names] + [row_id, organization_id], fetch="one")
        return merge(_normalize(dict(got))) if got else current

    def _where(self, table: str, filters: dict[str, Any], conds: list, params: list) -> None:
        typed_cols = split(table, {k: None for k in filters}) if filters else {}
        for k, v in filters.items():
            if k in typed_cols and k != "data":
                conds.append(sql.SQL("{} = %s").format(sql.Identifier(k)))
                params.append(v)
            elif table not in NO_DATA_COLUMN:
                conds.append(sql.SQL("data ->> %s = %s"))
                params.extend([k, str(v)])

    def list(self, table: str, *, organization_id: str, **filters: Any) -> list[Row]:
        t = self._table(table)
        conds = [sql.SQL("organization_id = %s")]
        params: list[Any] = [organization_id]
        self._where(table, filters, conds, params)
        q = sql.SQL("select * from {t} where {w} order by {o}").format(
            t=t, w=sql.SQL(" and ").join(conds),
            o=sql.Identifier(ORDER_COLUMN.get(table, "created_at")),
        )
        rows = self._run(q, params, fetch="all")
        return [merge(_normalize(dict(r))) for r in rows]

    def find_one(self, table: str, **filters: Any) -> Optional[Row]:
        if table not in GLOBAL_LOOKUP_TABLES:
            raise ValueError(f"find_one not permitted on {table}")
        t = self._table(table)
        conds: list = []
        params: list[Any] = []
        self._where(table, filters, conds, params)
        q = sql.SQL("select * from {t} where {w} limit 1").format(
            t=t, w=sql.SQL(" and ").join(conds) if conds else sql.SQL("true")
        )
        got = self._run(q, params, fetch="one")
        return merge(_normalize(dict(got))) if got else None

    def list_organization_ids(self) -> list[str]:
        rows = self._run(sql.SQL("select id from organizations order by created_at"), [], fetch="all")
        return [r["id"] for r in rows]
