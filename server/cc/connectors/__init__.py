"""Provider connectors (PRD section 4)."""

from __future__ import annotations

from typing import Any

from .base import AssetRecord, Connector, ConnectorError, EventRecord, SyncResult
from .github import GitHubConnector
from .n8n import N8nConnector
from .supabase import SupabaseConnector
from .vercel import VercelConnector

PROVIDERS: dict[str, dict[str, Any]] = {
    "github":   {"label": "GitHub",   "secret_label": "Personal access token / App token", "fields": ["org", "repos"]},
    "vercel":   {"label": "Vercel",   "secret_label": "API token", "fields": ["team_id"]},
    "supabase": {"label": "Supabase", "secret_label": "Management API token", "fields": []},
    "n8n":      {"label": "n8n",      "secret_label": "Public API key", "fields": ["base_url"]},
}


def build(provider: str, secret: str, config: dict[str, Any]) -> Connector:
    if provider == "github":
        repos = config.get("repos") or []
        if isinstance(repos, str):
            repos = [x.strip() for x in repos.replace("\n", ",").split(",") if x.strip()]
        return GitHubConnector(secret, repos=repos, org=config.get("org", ""))
    if provider == "vercel":
        return VercelConnector(secret, team_id=config.get("team_id", ""))
    if provider == "supabase":
        return SupabaseConnector(secret)
    if provider == "n8n":
        return N8nConnector(secret, base_url=config.get("base_url", ""))
    raise ConnectorError(f"unknown provider: {provider}")


__all__ = ["AssetRecord", "Connector", "ConnectorError", "EventRecord", "SyncResult", "PROVIDERS", "build",
           "GitHubConnector", "VercelConnector", "SupabaseConnector", "N8nConnector"]
