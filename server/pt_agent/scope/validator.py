"""Egress / scope enforcement — PRD section 9 and acceptance criterion 1.

Every request, redirect and reconnection is validated against the approved
``ScopeVersion`` *before* it is allowed out. The validator also blocks private,
loopback, link-local and cloud-metadata destinations so the public scanner
cannot be turned into an SSRF primitive.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from ..models import ScopeVersion, TargetSpec
from .target import NormalizedTarget, TargetParseError, is_ip_literal, normalize

# Cloud metadata endpoints that must never be reachable from the scanner.
BLOCKED_HOST_LITERALS = {
    "metadata.google.internal",
    "metadata",
    "localhost",
}
BLOCKED_IP_LITERALS = {
    "169.254.169.254",   # AWS / GCP / Azure IMDS
    "fd00:ec2::254",     # AWS IMDS over IPv6
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    target: NormalizedTarget | None = None


def _is_internal_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _matches_target(nt: NormalizedTarget, spec: TargetSpec) -> bool:
    if nt.scheme != spec.scheme.lower():
        return False
    # Exact host match only — no implicit subdomain or wildcard (section 9).
    if nt.host != spec.host.strip().strip(".").lower():
        return False
    if nt.port not in spec.ports:
        return False
    for allowed in spec.allowed_paths:
        prefix = allowed if allowed.startswith("/") else "/" + allowed
        if nt.path == prefix or nt.path.startswith(prefix.rstrip("/") + "/"):
            return True
        if prefix == "/":
            return True
    return False


class EgressValidator:
    """Decides whether a single URL may be requested under a scope version."""

    def __init__(self, scope: ScopeVersion, *, allow_internal: bool = False):
        self.scope = scope
        # allow_internal is only ever set for an explicitly-configured internal
        # scanner component (PRD section 9); the public scanner keeps it False.
        self.allow_internal = allow_internal

    def check(self, url: str) -> Decision:
        try:
            nt = normalize(url)
        except TargetParseError as exc:
            return Decision(False, f"unparseable target: {exc}")

        # Hard SSRF guards — enforced regardless of the allowlist.
        if nt.host in BLOCKED_HOST_LITERALS and not self.allow_internal:
            return Decision(False, "blocked metadata/local host", nt)
        if is_ip_literal(nt.host):
            if nt.host in BLOCKED_IP_LITERALS:
                return Decision(False, "blocked metadata address", nt)
            if _is_internal_ip(nt.host) and not self.allow_internal:
                return Decision(False, "internal/loopback address blocked", nt)

        # Must match an explicitly approved target.
        for spec in self.scope.targets:
            if _matches_target(nt, spec):
                return Decision(True, "within approved scope", nt)

        return Decision(False, "target not in approved scope", nt)

    def check_redirect(self, from_url: str, to_url: str) -> Decision:
        """Redirects are re-validated as a fresh request (section 9)."""
        return self.check(to_url)

    def check_resolved(self, host: str, resolved_ips: list[str]) -> Decision:
        """DNS guard (section 9): an approved hostname that resolves to an
        internal, loopback, link-local or metadata address is refused, so a
        DNS change cannot move traffic from the approved target to a forbidden
        destination."""
        if self.allow_internal:
            return Decision(True, "internal targets explicitly allowed")
        for ip in resolved_ips:
            if ip in BLOCKED_IP_LITERALS or _is_internal_ip(ip):
                return Decision(False, f"{host} resolves to forbidden address {ip}")
        if not resolved_ips:
            return Decision(False, f"{host} did not resolve")
        return Decision(True, "resolved to public addresses")
