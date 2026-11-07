"""Connector contract (PRD section 4).

Each connector declares its capabilities, verifies access, and returns a
normalised inventory (assets) and activity (events). Only allow-listed fields
are returned: identifiers, names, timestamps, statuses and links. Never
payloads, logs, env vars or message contents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol

import httpx


@dataclass
class AssetRecord:
    external_id: str
    kind: str
    name: str
    environment: str = "unclassified"
    state: str = ""
    url: str = ""
    description: str = ""
    source_updated_at: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)   # allow-listed small fields only


@dataclass
class EventRecord:
    external_id: str
    asset_external_id: str
    kind: str
    result: str
    occurred_at: str
    title: str = ""
    environment: str = "unclassified"
    url: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncResult:
    assets: list[AssetRecord] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)
    coverage: dict[str, str] = field(default_factory=dict)   # capability -> full | partial | inventory_only | blocked
    notes: list[str] = field(default_factory=list)
    partial: bool = False


class ConnectorError(RuntimeError):
    def __init__(self, message: str, *, status: str = "disconnected"):
        super().__init__(message)
        self.status = status   # reauth | rate_limited | disconnected | partial


class Connector(Protocol):
    provider: str

    def verify(self) -> dict[str, Any]: ...
    def sync(self, *, since: Optional[datetime] = None) -> SyncResult: ...


def make_client(headers: dict[str, str], *, timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": "control-center/0.1", **headers})


def classify_http_error(r: httpx.Response) -> ConnectorError:
    if r.status_code in (401, 403):
        return ConnectorError(f"authorization failed ({r.status_code})", status="reauth")
    if r.status_code == 429:
        return ConnectorError("rate limited", status="rate_limited")
    # Status only: an upstream body is never stored or shown (it could contain
    # internal detail, and it is what an SSRF probe would want reflected).
    return ConnectorError(f"provider error {r.status_code}", status="error")
