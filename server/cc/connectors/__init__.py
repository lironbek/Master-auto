"""Provider connectors (PRD section 4)."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

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


class ConfigError(ValueError):
    """Connection config refused before any request is made."""


def _is_internal(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast or a.is_unspecified


def validate_base_url(url: str) -> str:
    """A user-supplied instance URL (n8n) must be a public https origin. The
    server performs requests to it with the stored key, so loopback, private,
    link-local and metadata addresses are refused (SSRF guard), as are
    credentials in the URL and non-standard ports."""
    url = (url or "").strip()
    if not url:
        raise ConfigError("base_url is required")
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise ConfigError("base_url must start with https://")
    if not parts.hostname or "@" in parts.netloc:
        raise ConfigError("base_url must be a plain https host without credentials")
    if parts.port not in (None, 443):
        raise ConfigError("base_url must use the default https port")
    host = parts.hostname.lower().rstrip(".")
    if host in ("localhost", "metadata", "metadata.google.internal") or host.endswith(".internal") or host.endswith(".local"):
        raise ConfigError("base_url must be a public host")
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(host, 443)}
    except socket.gaierror:
        raise ConfigError("base_url host does not resolve")
    if not addrs or any(_is_internal(a) for a in addrs):
        raise ConfigError("base_url resolves to a private or reserved address")
    return f"https://{host}" + (parts.path.rstrip("/") if parts.path not in ("", "/") else "")


def validate_config(provider: str, config: dict[str, Any]) -> dict[str, Any]:
    """Validate (and normalise in place) the per-provider config. Raises
    :class:`ConfigError`; the HTTP layer maps it to 422."""
    if provider == "n8n":
        config["base_url"] = validate_base_url(str(config.get("base_url", "")))
    return config


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
        # Re-validated at sync time too: config is data, not trust.
        return N8nConnector(secret, base_url=validate_base_url(str(config.get("base_url", ""))))
    raise ConnectorError(f"unknown provider: {provider}")


__all__ = ["AssetRecord", "Connector", "ConnectorError", "ConfigError", "EventRecord", "SyncResult", "PROVIDERS",
           "build", "validate_config", "validate_base_url",
           "GitHubConnector", "VercelConnector", "SupabaseConnector", "N8nConnector"]
