"""Pull the old billing system's data straight out of its Supabase project.

The old app talked to Supabase from the browser, so the same two public
pieces (project URL + anon key) plus a user login are enough to read every
table through PostgREST under that user's RLS. Nothing is stored here: the
credentials live only for the duration of one request.
"""

from __future__ import annotations

from typing import Any

import httpx

TABLES = ["customers", "products", "services", "product_users", "employees", "service_tickets", "service_time_entries",
          "external_ticket_updates", "monthly_summaries", "billing_items", "expenses", "knowledge_items"]
PAGE = 1000


class LegacyError(Exception):
    pass


def _base(url: str) -> str:
    u = url.strip().rstrip("/")
    if not u.startswith("https://") or ".supabase.co" not in u:
        raise LegacyError("כתובת Supabase לא תקינה (נדרש https://<ref>.supabase.co)")
    return u


def login(url: str, anon_key: str, email: str, password: str, *, client: httpx.Client) -> str:
    r = client.post(f"{_base(url)}/auth/v1/token", params={"grant_type": "password"}, headers={"apikey": anon_key, "Content-Type": "application/json"},
                    json={"email": email, "password": password})
    if r.status_code != 200:
        detail = ""
        try:
            detail = r.json().get("error_description") or r.json().get("msg") or r.json().get("message") or ""
        except Exception:
            pass
        raise LegacyError(f"ההתחברות ל-Supabase הישן נכשלה ({r.status_code}) {detail}".strip())
    token = r.json().get("access_token")
    if not token:
        raise LegacyError("ההתחברות לא החזירה טוקן")
    return token


def fetch_table(url: str, anon_key: str, token: str, table: str, *, client: httpx.Client) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    headers = {"apikey": anon_key, "Authorization": f"Bearer {token}", "Accept": "application/json"}
    while True:
        r = client.get(f"{_base(url)}/rest/v1/{table}", params={"select": "*", "limit": PAGE, "offset": offset}, headers=headers)
        if r.status_code == 404:
            return []            # table does not exist in this project
        if r.status_code != 200:
            raise LegacyError(f"קריאת {table} נכשלה ({r.status_code}): {r.text[:200]}")
        rows = r.json()
        out.extend(rows)
        if len(rows) < PAGE:
            return out
        offset += PAGE


def fetch_all(url: str, anon_key: str, email: str, password: str) -> dict[str, list[dict[str, Any]]]:
    with httpx.Client(timeout=60.0) as client:
        token = login(url, anon_key, email, password, client=client)
        return {t: fetch_table(url, anon_key, token, t, client=client) for t in TABLES}
