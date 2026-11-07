"""Target normalisation — PRD section 9.

Addresses, ports and hostnames are normalised *before* matching against the
allowlist, so that encoding tricks cannot smuggle a request past the boundary.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit, unquote

DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class NormalizedTarget:
    scheme: str
    host: str          # lower-case, trailing dot stripped, IDNA-encoded
    port: int
    path: str          # percent-decoded, collapsed
    raw: str

    @property
    def host_port(self) -> str:
        return f"{self.host}:{self.port}"


class TargetParseError(ValueError):
    """Raised when a URL cannot be normalised into a comparable target."""


def _normalize_host(host: str) -> str:
    host = host.strip().strip(".").lower()
    if not host:
        raise TargetParseError("empty host")
    # Strip userinfo if it slipped in via the authority component.
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    try:
        # IDNA so unicode look-alikes collapse to their ascii form.
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        # Not an IDNA hostname (e.g. a literal IP); keep the lowercased form.
        pass
    return host


def normalize(url: str) -> NormalizedTarget:
    """Parse and canonicalise *url* into a comparable target.

    Raises :class:`TargetParseError` for inputs that are structurally unsafe to
    compare (missing scheme/host, unsupported scheme).
    """

    if not url or "://" not in url:
        raise TargetParseError(f"not an absolute url: {url!r}")

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        raise TargetParseError(f"unsupported scheme: {scheme!r}")

    host = _normalize_host(parts.hostname or "")
    port = parts.port or DEFAULT_PORTS[scheme]

    # Percent-decode and collapse the path for prefix comparison.
    path = unquote(parts.path or "/")
    while "//" in path:
        path = path.replace("//", "/")
    if not path.startswith("/"):
        path = "/" + path

    return NormalizedTarget(scheme=scheme, host=host, port=port, path=path, raw=url)


def is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False
