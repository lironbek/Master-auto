"""Tool Gateway — PRD section 15.

Only approved, schema-bound modules may run, and only through this gateway.
Every call is validated against the egress boundary and the policy engine
before execution. This file ships *passive / structural* reference modules
only; active exploitation modules are intentionally out of scope for this
repository (see README "Scope of this implementation").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from ..scope import EgressValidator


@dataclass
class ModuleResult:
    module: str
    target: str
    observations: list[str]
    raw_for_redaction: str = ""   # passed through redaction before storage


class TestModule(Protocol):
    name: str

    def run(self, target: str, fetch: "FetchFn") -> ModuleResult: ...


# A fetch function is injected by the Runner; the gateway never opens sockets
# itself. The Runner's fetch is the only path to the network and is wrapped by
# the Egress service.
FetchFn = Callable[[str], str]


class GatewayError(RuntimeError):
    pass


class ToolGateway:
    def __init__(self, validator: EgressValidator):
        self._validator = validator
        self._modules: dict[str, TestModule] = {}

    def register(self, module: TestModule) -> None:
        self._modules[module.name] = module

    def available(self) -> list[str]:
        return sorted(self._modules)

    def run(self, module_name: str, target: str, fetch: FetchFn) -> ModuleResult:
        if module_name not in self._modules:
            raise GatewayError(f"unknown or unapproved module: {module_name}")
        decision = self._validator.check(target)
        if not decision.allowed:
            raise GatewayError(f"egress blocked: {decision.reason}")
        return self._modules[module_name].run(target, fetch)


# --- Passive reference modules ---------------------------------------------

class SecurityHeadersModule:
    """Passive: inspect response headers for common hardening gaps.

    This only reads headers that a normal browser receives; it changes nothing.
    """

    name = "passive.security_headers"

    def run(self, target: str, fetch: FetchFn) -> ModuleResult:
        body = fetch(target)
        observations: list[str] = []
        lowered = body.lower()
        for header in (
            "strict-transport-security",
            "content-security-policy",
            "x-content-type-options",
            "x-frame-options",
        ):
            if header not in lowered:
                observations.append(f"missing header: {header}")
        return ModuleResult(
            module=self.name,
            target=target,
            observations=observations or ["all inspected headers present"],
            raw_for_redaction=body,
        )


class CookieFlagsModule:
    """Passive: note cookies lacking Secure/HttpOnly in observed Set-Cookie."""

    name = "passive.cookie_flags"

    def run(self, target: str, fetch: FetchFn) -> ModuleResult:
        body = fetch(target)
        observations: list[str] = []
        for line in body.splitlines():
            if line.lower().startswith("set-cookie:"):
                low = line.lower()
                if "secure" not in low:
                    observations.append("cookie without Secure flag observed")
                if "httponly" not in low:
                    observations.append("cookie without HttpOnly flag observed")
        return ModuleResult(
            module=self.name,
            target=target,
            observations=observations or ["no cookie flag issues observed"],
            raw_for_redaction=body,
        )
