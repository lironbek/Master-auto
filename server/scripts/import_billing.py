#!/usr/bin/env python3
"""Import the old billing system (Lovable + Supabase) into the control center.

Input: a folder with CSV exports from the old Supabase project, one file per
table, named exactly like the table (customers.csv, products.csv,
product_users.csv, services.csv, employees.csv, service_tickets.csv,
service_time_entries.csv, external_ticket_updates.csv, monthly_summaries.csv,
billing_items.csv, expenses.csv, knowledge_items.csv). Missing files are
skipped. Supabase Dashboard -> Table Editor -> "Export as CSV" produces the
right format; JSON exports (one array per file) work too.

Usage:
  python scripts/import_billing.py --dir ./export --base https://master-auto-api.vercel.app \
      --email you@example.com --workspace <workspace id> [--dry-run]

The password is read from the BILLING_IMPORT_PASSWORD environment variable or
prompted for. The import is idempotent: rows already imported (by legacy id)
are skipped, so it can be re-run after a final delta export.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import os
import sys
from pathlib import Path

import httpx

TABLES = ["customers", "products", "services", "product_users", "employees", "service_tickets", "service_time_entries",
          "external_ticket_updates", "monthly_summaries", "billing_items", "expenses", "knowledge_items"]
BOOL_COLS = {"paid", "recurring", "has_light_user"}
NUM_COLS = {"price", "light_user_price", "user_count", "light_user_count", "time_spent", "treatment_time", "total_amount", "price_per_unit",
            "quantity", "amount", "amount_in_ils", "hourly_rate", "month", "year"}


def _coerce(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if v in ("", None, "NULL", "null"):
            out[k] = None
        elif k in BOOL_COLS:
            out[k] = str(v).strip().lower() in ("true", "t", "1", "yes")
        elif k in NUM_COLS:
            try:
                out[k] = float(v) if "." in str(v) else int(v)
            except ValueError:
                out[k] = None
        elif k == "tags" and isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                try:
                    out[k] = json.loads(s)
                    continue
                except ValueError:
                    pass
            out[k] = [x.strip().strip('"') for x in s.strip("{}").split(",") if x.strip()]
        else:
            out[k] = v
    return out


def load(folder: Path, table: str) -> list[dict]:
    for ext in ("csv", "json"):
        f = folder / f"{table}.{ext}"
        if f.exists():
            if ext == "csv":
                with f.open(encoding="utf-8-sig", newline="") as fh:
                    return [_coerce(r) for r in csv.DictReader(fh)]
            return [_coerce(r) for r in json.loads(f.read_text(encoding="utf-8"))]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--base", default="https://master-auto-api.vercel.app")
    ap.add_argument("--email", required=True)
    ap.add_argument("--workspace", required=True, help="workspace id the billing module lives in")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    folder = Path(args.dir)
    payload = {"workspace_id": args.workspace}
    for t in TABLES:
        rows = load(folder, t)
        payload[t] = rows
        print(f"{t:26s} {len(rows):6d} rows")
    if args.dry_run:
        print("dry run, nothing sent")
        return 0
    password = os.environ.get("BILLING_IMPORT_PASSWORD") or getpass.getpass("password: ")
    with httpx.Client(base_url=args.base, timeout=120) as c:
        r = c.post("/auth/login", json={"email": args.email, "password": password})
        r.raise_for_status()
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        r = c.post("/billing/import", json=payload, headers=h)
        if r.status_code != 200:
            print("import failed:", r.status_code, r.text, file=sys.stderr)
            return 1
        rep = r.json()["report"]
        print("\nresult (inserted / skipped / errors):")
        for k, v in rep.items():
            print(f"  {k:26s} {v['inserted']:6d} / {v['skipped']:6d} / {v['errors']:6d}")
        if any(v["errors"] for v in rep.values()):
            print("some rows could not be imported (missing parent rows). Fix the export and re-run; already imported rows are skipped.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
