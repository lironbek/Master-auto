"""Untrusted-content handling — PRD section 7 (מגבלות הקשר) and AC 3.

Site content, files and tool results are untrusted. An instruction appearing in
them — to ignore policy, send a secret, or test another domain — is recorded
and never acted on. This module detects such injection attempts so the agent
loop can log them as observations rather than follow them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_INJECTION_SIGNALS = [
    re.compile(r"(?i)ignore (all|any|previous|above).{0,30}(instruction|policy|rule)"),
    re.compile(r"(?i)disregard.{0,30}(instruction|policy|scope)"),
    re.compile(r"(?i)(send|exfiltrate|post|email).{0,30}(secret|password|token|key)"),
    re.compile(r"(?i)(scan|test|attack|pentest).{0,30}(this|the following|another) (domain|host|site|url)"),
    re.compile(r"(?i)you are now|new system prompt|act as (?:an? )?(?:admin|root)"),
    re.compile(r"(?i)add .{0,20}to (the )?(scope|allowlist)"),
]


@dataclass
class InjectionReport:
    detected: bool
    signals: list[str]

    def as_observation(self) -> str:
        if not self.detected:
            return ""
        return (
            "Prompt-injection attempt observed in untrusted content and ignored: "
            + "; ".join(self.signals)
        )


def scan_untrusted(text: str) -> InjectionReport:
    hits = [p.pattern for p in _INJECTION_SIGNALS if p.search(text or "")]
    return InjectionReport(detected=bool(hits), signals=hits)
