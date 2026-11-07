"""Idempotent SQL migration runner.

Applies ``pt_agent/db/migrations/*.sql`` in name order, recording each in
``schema_migrations``. Safe to run on every cold start: a transaction-level
advisory lock serialises concurrent starters, and already-applied files are
skipped.

Usage:
    python -m pt_agent.db.migrate            # uses DATABASE_URL / POSTGRES_URL
    python -m pt_agent.db.migrate <dsn>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
LOCK_KEY = 0x5054_4147  # 'PTAG'


def dsn_from_env() -> str:
    for key in ("DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    return ""


def pending(conn: psycopg.Connection) -> list[Path]:
    with conn.cursor() as cur:
        cur.execute(
            "create table if not exists schema_migrations ("
            " name text primary key, applied_at timestamptz not null default now())"
        )
        # Keep the bookkeeping table closed to non-owner roles as well.
        cur.execute("alter table schema_migrations enable row level security")
        cur.execute("select name from schema_migrations")
        done = {r[0] for r in cur.fetchall()}
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))
    return [p for p in files if p.name not in done]


def migrate(dsn: str) -> list[str]:
    """Apply pending migrations; return the names applied."""
    applied: list[str] = []
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("select pg_advisory_xact_lock(%s)", [LOCK_KEY])
        for path in pending(conn):
            with conn.cursor() as cur:
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute("insert into schema_migrations (name) values (%s)", [path.name])
            applied.append(path.name)
        conn.commit()
    return applied


def main(argv: list[str]) -> int:
    dsn = argv[1] if len(argv) > 1 else dsn_from_env()
    if not dsn:
        print("no DSN: set DATABASE_URL or pass one as an argument", file=sys.stderr)
        return 2
    names = migrate(dsn)
    print("applied:", names or "nothing (up to date)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
