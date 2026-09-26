"""IdentityService — local accounts and server-side sessions.

Staff in production authenticate through Microsoft Entra ID (OIDC); the
resulting claims (subject, `amr`, device id) are mapped onto the same
`AuthContext`, so nothing downstream depends on how a user signed in.
"""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import FrozenSet, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import clock
from app.core.errors import DomainError, NotAuthenticated
from app.core.rbac import permissions_for
from app.core.security import new_token, token_hash, verify_password
from app.models import AuthSession, Role, SupplierContact, User, UserRole
from app.services import audit
from app.services.audit import Actor

# Role shown on audit events when a user holds several — most specific first.
_ROLE_PRIORITY = [
    "procurement_manager", "tender_committee", "scholarship_admin", "scholarship_committee",
    "auditor", "system_admin", "supplier", "applicant",
]


@dataclass
class AuthContext:
    user: User
    session_id: uuid.UUID
    role_keys: FrozenSet[str]
    permissions: FrozenSet[str]
    amr: List[str] = field(default_factory=list)
    ip: Optional[str] = None
    supplier_id: Optional[uuid.UUID] = None

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def primary_role(self) -> Optional[str]:
        for key in _ROLE_PRIORITY:
            if key in self.role_keys:
                return key
        return None

    @property
    def mfa(self) -> bool:
        return "mfa" in self.amr or "otp" in self.amr

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def actor(self) -> Actor:
        return Actor(self.user.id, self.primary_role, self.ip)


def active_role_keys(db: Session, user_id: uuid.UUID) -> FrozenSet[str]:
    rows = db.execute(
        select(Role.key).join(UserRole, UserRole.role_id == Role.id).where(
            UserRole.user_id == user_id, UserRole.revoked_at.is_(None)
        )
    ).scalars()
    return frozenset(rows)


def _create_session(db: Session, user: User, ip: Optional[str], user_agent: Optional[str], amr: List[str]) -> Tuple[str, str]:
    settings = get_settings()
    token = new_token()
    csrf = secrets.token_urlsafe(24)
    now = clock.now()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_hash(token),
            csrf_token=csrf,
            amr=amr,
            ip=ip,
            user_agent=(user_agent or "")[:300],
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=settings.session_absolute_hours),
        )
    )
    user.last_login_at = now
    return token, csrf


def login(db: Session, email: str, password: str, ip: Optional[str], user_agent: Optional[str]) -> Tuple[str, str, User]:
    user = db.execute(select(User).where(User.email == email.strip().lower())).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        audit.record_independent(
            "LOGIN_FAILED", Actor(user.id if user else None, None, ip), metadata={"reason": "invalid_credentials"}
        )
        raise DomainError("invalid_credentials", "Email or password is incorrect", status_code=401)
    token, csrf = _create_session(db, user, ip, user_agent, ["pwd"])
    audit.record(db, "USER_LOGGED_IN", Actor(user.id, None, ip), metadata={"method": "password"})
    db.commit()
    return token, csrf, user


def demo_login(db: Session, user_id: uuid.UUID, ip: Optional[str], user_agent: Optional[str]) -> Tuple[str, str, User]:
    if not get_settings().demo_enabled:
        raise DomainError("not_found", "Not found", status_code=404)
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise DomainError("not_found", "Not found", status_code=404)
    # A demo sign-in never claims MFA: step-up still applies where a policy asks for it.
    token, csrf = _create_session(db, user, ip, user_agent, ["demo"])
    audit.record(db, "USER_LOGGED_IN", Actor(user.id, None, ip), metadata={"method": "demo"})
    db.commit()
    return token, csrf, user


def resolve(db: Session, token: Optional[str], ip: Optional[str]) -> AuthContext:
    if not token:
        raise NotAuthenticated()
    session = db.execute(select(AuthSession).where(AuthSession.token_hash == token_hash(token))).scalar_one_or_none()
    now = clock.now()
    settings = get_settings()
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at <= now
        or session.last_seen_at + timedelta(minutes=settings.session_idle_minutes) <= now
    ):
        raise NotAuthenticated("Session expired")
    user = session.user
    if not user.is_active:
        raise NotAuthenticated("Account disabled")
    if (now - session.last_seen_at).total_seconds() > 60:
        session.last_seen_at = now
        db.commit()
    roles = active_role_keys(db, user.id)
    supplier_id = None
    if "supplier" in roles:
        supplier_id = db.execute(
            select(SupplierContact.supplier_id).where(SupplierContact.user_id == user.id)
        ).scalar_one_or_none()
    return AuthContext(
        user=user,
        session_id=session.id,
        role_keys=roles,
        permissions=permissions_for(roles),
        amr=list(session.amr or []),
        ip=ip,
        supplier_id=supplier_id,
    )


def csrf_for(db: Session, session_id: uuid.UUID) -> str:
    return db.get(AuthSession, session_id).csrf_token


def logout(db: Session, ctx: AuthContext) -> None:
    session = db.get(AuthSession, ctx.session_id)
    if session and session.revoked_at is None:
        session.revoked_at = clock.now()
        audit.record(db, "USER_LOGGED_OUT", ctx.actor())
        db.commit()
