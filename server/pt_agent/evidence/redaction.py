"""Redaction — PRD section 10.

Secrets, passwords and identifying data are redacted *in memory before* anything
is written to a log, report, URL or model prompt. The raw value never leaves
this layer. For comparing recurrences, a keyed HMAC fingerprint is used — not a
plain hash of a weak password (PRD section 10, final paragraph).

If redaction fails, the caller must block the save and alert the survey
manager (PRD section 10.2 and acceptance criterion 6).
"""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass, field
from hashlib import sha256

REDACTED = "[REDACTED]"

# Patterns for high-signal secrets. Order matters: more specific first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")),
    ("bearer", re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{8,}")),
    ("private_key", re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
        re.DOTALL,
    )),
    ("api_key_kv", re.compile(
        r"(?i)\b(api[_-]?key|apikey|secret|token|passwd|password|pwd)\b\s*[=:]\s*[\"']?([^\s\"'&]{4,})",
    )),
    ("authorization_header", re.compile(r"(?im)^(authorization)\s*:\s*.+$")),
    ("set_cookie", re.compile(r"(?im)^(set-cookie|cookie)\s*:\s*.+$")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
]


class RedactionError(RuntimeError):
    """Raised when redaction cannot be completed; callers must fail closed."""


@dataclass
class RedactionResult:
    text: str
    fingerprints: dict[str, list[str]] = field(default_factory=dict)
    hit_kinds: list[str] = field(default_factory=list)

    @property
    def had_secrets(self) -> bool:
        return bool(self.hit_kinds)


def fingerprint(value: str, *, org_key: bytes) -> str:
    """Keyed HMAC fingerprint of a secret value.

    The organisation key is held separately from evidence storage (PRD section
    10.2). A plain hash is explicitly rejected by the PRD because weak passwords
    would be trivially reversible.
    """
    if not org_key:
        raise RedactionError("organisation HMAC key is required for fingerprinting")
    return hmac.new(org_key, value.encode("utf-8"), sha256).hexdigest()


def redact(text: str, *, org_key: bytes | None = None) -> RedactionResult:
    """Redact *text* and return the cleaned string plus optional fingerprints.

    Raises :class:`RedactionError` on bad input so callers can fail closed.
    """
    if text is None:
        raise RedactionError("cannot redact None")

    result = RedactionResult(text=text)

    for kind, pattern in _PATTERNS:
        def _replace(match: re.Match[str]) -> str:
            raw = match.group(0)
            if org_key is not None:
                # Fingerprint the most secret capture group available.
                secret = match.groups()[-1] if match.groups() else raw
                result.fingerprints.setdefault(kind, []).append(
                    fingerprint(secret, org_key=org_key)
                )
            # Preserve a leading label (e.g. "password=") for readability.
            if match.groups() and match.group(1) and "=" in raw or ":" in raw:
                label = match.group(1)
                sep = "=" if "=" in raw else ":"
                return f"{label}{sep}{REDACTED}"
            return REDACTED

        new_text, n = pattern.subn(_replace, result.text)
        if n:
            result.hit_kinds.append(kind)
            result.text = new_text

    return result


def assert_clean(text: str) -> None:
    """Guard used before persisting: raise if any known secret pattern remains.

    This enforces acceptance criterion 6 — a synthetic secret marker must not
    appear raw in logs, prompts, reports or screenshots.
    """
    # A match that already contains the placeholder (e.g. "password=[REDACTED]")
    # is not a leftover. Do not strip the placeholder first: that would let a
    # pattern bridge across it to innocent following text.
    leftovers = []
    for kind, pattern in _PATTERNS:
        if kind in {"email"}:  # emails are redacted but not blocking on their own
            continue
        if any(REDACTED not in m.group(0) for m in pattern.finditer(text)):
            leftovers.append(kind)
    if leftovers:
        raise RedactionError(f"unredacted secrets remain: {', '.join(leftovers)}")
