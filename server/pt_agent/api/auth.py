"""Authentication and roles — PRD sections 3 and 19.

- Email + password (scrypt, stdlib) with opaque bearer session tokens.
- The organisation of every request is derived from the session, never from a
  client-supplied header (acceptance criterion 2).
- Roles follow PRD section 3. The first user of an organisation is its admin.

Tests may opt into the legacy ``X-Org-Id`` header with
``PT_ALLOW_HEADER_AUTH=1``; it is ignored in deployment.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..models import Membership, Organization, Role, User
from ..storage import get_store

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_HOURS = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- password hashing (scrypt, stdlib) --------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- principal ----------------------------------------------------------------

@dataclass
class Principal:
    organization_id: str
    user_id: str
    email: str
    display_name: str
    role: Role

    @property
    def actor(self) -> str:
        return self.email or self.user_id


def _header_auth_enabled() -> bool:
    """The legacy X-Org-Id header is a test convenience only: it is honoured
    solely for the in-memory store and never on a hosted deployment, whatever
    the flag says."""
    if os.environ.get("PT_ALLOW_HEADER_AUTH") != "1":
        return False
    from ..storage import backend_name

    hosted = any(os.environ.get(k) for k in ("VERCEL", "VERCEL_ENV", "DATABASE_URL", "POSTGRES_URL", "SUPABASE_URL"))
    return backend_name() == "memory" and not hosted


def current_principal(
    authorization: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None),
) -> Principal:
    store = get_store()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        sess = store.find_one("sessions", token_hash=_token_hash(token))
        if not sess:
            raise HTTPException(status_code=401, detail="invalid session")
        exp = sess.get("expires_at")
        exp_dt = datetime.fromisoformat(exp) if isinstance(exp, str) else exp
        if exp_dt is not None and exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if exp_dt is not None and exp_dt < _now():
            raise HTTPException(status_code=401, detail="session expired")
        user = store.get("users", sess["user_id"], organization_id=sess["organization_id"])
        if not user:
            raise HTTPException(status_code=401, detail="unknown user")
        mem = store.list("memberships", organization_id=sess["organization_id"], user_id=user["id"])
        role = Role(mem[0]["role"]) if mem else Role.DEVELOPER
        return Principal(sess["organization_id"], user["id"], user["email"], user.get("display_name", ""), role)

    if x_org_id and _header_auth_enabled():
        return Principal(x_org_id, "header", "header@local", "header auth", Role.ORG_ADMIN)

    raise HTTPException(status_code=401, detail="authentication required")


def require_role(*roles: Role):
    def _dep(p: Principal = Depends(current_principal)) -> Principal:
        if p.role not in roles:
            raise HTTPException(status_code=403, detail="insufficient role")
        return p

    return _dep


# --- endpoints ----------------------------------------------------------------

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _HasEmail(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("invalid email")
        return v


class RegisterOrg(_HasEmail):
    organization_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = ""


class Login(_HasEmail):
    password: str


class CreateUser(_HasEmail):
    password: str = Field(min_length=8, max_length=200)
    display_name: str = ""
    role: Role = Role.PT_TESTER


def _issue_session(org_id: str, user_id: str) -> dict:
    token = secrets.token_urlsafe(32)
    get_store().insert("sessions", {
        "id": f"ses_{secrets.token_hex(8)}",
        "organization_id": org_id,
        "user_id": user_id,
        "token_hash": _token_hash(token),
        "expires_at": (_now() + timedelta(hours=SESSION_HOURS)).isoformat(),
        "created_at": _now().isoformat(),
    })
    return {"token": token, "expires_in_hours": SESSION_HOURS}


@router.post("/register-org")
def register_org(body: RegisterOrg):
    """Create an organisation and its first (admin) user.

    Disabled with ``PT_ALLOW_SELF_REGISTER=0`` once the platform is seeded.
    """
    if os.environ.get("PT_ALLOW_SELF_REGISTER", "1") == "0":
        raise HTTPException(status_code=403, detail="self-registration disabled")
    store = get_store()
    if store.find_one("users", email=body.email.lower()):
        raise HTTPException(status_code=409, detail="email already registered")
    org = Organization(name=body.organization_name)
    store.insert("organizations", org.model_dump(mode="json"))
    user = User(organization_id=org.id, email=body.email.lower(), display_name=body.display_name)
    row = user.model_dump(mode="json")
    row["password_hash"] = hash_password(body.password)
    store.insert("users", row)
    store.insert("memberships", Membership(
        organization_id=org.id, user_id=user.id, role=Role.ORG_ADMIN
    ).model_dump(mode="json"))
    out = _issue_session(org.id, user.id)
    out.update({"organization": {"id": org.id, "name": org.name},
                "user": {"id": user.id, "email": user.email, "display_name": user.display_name,
                         "role": Role.ORG_ADMIN.value}})
    return out


@router.post("/login")
def login(body: Login):
    store = get_store()
    user = store.find_one("users", email=body.email.lower())
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="invalid credentials")
    mem = store.list("memberships", organization_id=user["organization_id"], user_id=user["id"])
    role = mem[0]["role"] if mem else Role.DEVELOPER.value
    org = store.find_one("organizations", id=user["organization_id"]) or {}
    out = _issue_session(user["organization_id"], user["id"])
    out.update({"organization": {"id": user["organization_id"], "name": org.get("name", "")},
                "user": {"id": user["id"], "email": user["email"],
                         "display_name": user.get("display_name", ""), "role": role}})
    return out


@router.get("/me")
def me(p: Principal = Depends(current_principal)):
    org = get_store().find_one("organizations", id=p.organization_id) or {}
    return {"organization": {"id": p.organization_id, "name": org.get("name", "")},
            "user": {"id": p.user_id, "email": p.email, "display_name": p.display_name,
                     "role": p.role.value}}


@router.post("/logout")
def logout(authorization: Optional[str] = Header(default=None), p: Principal = Depends(current_principal)):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        sess = get_store().find_one("sessions", token_hash=_token_hash(token))
        if sess:
            get_store().update("sessions", sess["id"], organization_id=p.organization_id,
                               patch={"expires_at": _now().isoformat()})
    return {"ok": True}


@router.post("/users")
def create_user(body: CreateUser, p: Principal = Depends(require_role(Role.ORG_ADMIN))):
    store = get_store()
    if store.find_one("users", email=body.email.lower()):
        raise HTTPException(status_code=409, detail="email already registered")
    user = User(organization_id=p.organization_id, email=body.email.lower(), display_name=body.display_name)
    row = user.model_dump(mode="json")
    row["password_hash"] = hash_password(body.password)
    store.insert("users", row)
    store.insert("memberships", Membership(
        organization_id=p.organization_id, user_id=user.id, role=body.role
    ).model_dump(mode="json"))
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": body.role.value}


@router.get("/users")
def list_users(p: Principal = Depends(current_principal)):
    store = get_store()
    users = store.list("users", organization_id=p.organization_id)
    mems = {m["user_id"]: m["role"] for m in store.list("memberships", organization_id=p.organization_id)}
    return [{"id": u["id"], "email": u["email"], "display_name": u.get("display_name", ""),
             "role": mems.get(u["id"], "")} for u in users]
