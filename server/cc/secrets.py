"""Server-side secret storage (PRD section 6, "נתונים וסודות").

Provider tokens and AI keys are encrypted with a key held only by the server
(``CC_SECRET_KEY``, a Fernet key). The plaintext is never returned by the API;
only a masked suffix is shown. Without a key configured, storing a secret is
refused rather than stored in clear.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class SecretsUnavailable(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = os.environ.get("CC_SECRET_KEY", "").strip()
    if not key:
        raise SecretsUnavailable("CC_SECRET_KEY is not configured; refusing to store secrets in clear")
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretsUnavailable("stored secret cannot be decrypted with the current key") from exc


def mask(value: str) -> str:
    v = value.strip()
    return "••••" + v[-4:] if len(v) >= 4 else "••••"


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")
