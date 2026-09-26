"""User and role administration with separation-of-duties guards."""
from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import Conflict, Forbidden, Invalid, NotFound
from app.core.rbac import PERMISSIONS, ROLES
from app.core.security import hash_password
from app.models import Permission, Role, RolePermission, User, UserRole
from app.services import audit, authorization, notifications
from app.services.identity import AuthContext, active_role_keys
from app.services.suppliers import default_organization


def sync_rbac(db: Session) -> None:
    """Mirror app.core.rbac into the tables (idempotent)."""
    for key, description in PERMISSIONS.items():
        existing = db.get(Permission, key)
        if existing is None:
            db.add(Permission(key=key, description=description))
        else:
            existing.description = description
    db.flush()
    for key, spec in ROLES.items():
        role = db.execute(select(Role).where(Role.key == key)).scalar_one_or_none()
        if role is None:
            role = Role(id=uuid.uuid4(), key=key)
            db.add(role)
        role.name_he, role.name_ar, role.name_en = spec["names"]
        role.is_business_role = spec["business"]
        db.flush()
        wanted = set(spec["permissions"])
        current = set(db.execute(select(RolePermission.permission_key).where(RolePermission.role_id == role.id)).scalars())
        for perm in wanted - current:
            db.add(RolePermission(role_id=role.id, permission_key=perm))
        for perm in current - wanted:
            db.execute(RolePermission.__table__.delete().where(
                RolePermission.role_id == role.id, RolePermission.permission_key == perm))
    db.flush()


def list_users(db: Session, ctx: AuthContext, kind: Optional[str] = None) -> List[dict]:
    authorization.require(ctx, "user.manage")
    stmt = select(User).order_by(User.kind, User.full_name)
    if kind:
        stmt = stmt.where(User.kind == kind)
    users = db.execute(stmt).scalars().all()
    return [
        {"id": str(u.id), "email": u.email, "full_name": u.full_name, "kind": u.kind, "is_active": u.is_active,
         "locale": u.locale, "roles": sorted(active_role_keys(db, u.id)),
         "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}
        for u in users
    ]


def create_staff_user(db: Session, ctx: AuthContext, *, email: str, full_name: str, password: Optional[str],
                      locale: str = "he") -> User:
    authorization.require(ctx, "user.manage")
    email = email.strip().lower()
    if db.execute(select(User.id).where(User.email == email)).first():
        raise Conflict("email_taken", "An account with this email already exists")
    user = User(id=uuid.uuid4(), organization_id=default_organization(db).id, email=email, full_name=full_name.strip(),
                kind="staff", password_hash=hash_password(password) if password else None, locale=locale,
                created_at=clock.now())
    db.add(user)
    db.flush()
    audit.record(db, "USER_CREATED", ctx.actor(), metadata={"user_id": user.id, "kind": "staff"})
    return user


def set_active(db: Session, ctx: AuthContext, user_id: uuid.UUID, active: bool) -> None:
    authorization.require(ctx, "user.manage")
    if user_id == ctx.user_id:
        raise Forbidden("self_change_forbidden", "You cannot deactivate your own account")
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("user")
    user.is_active = active
    audit.record(db, "USER_ACTIVATED" if active else "USER_DEACTIVATED", ctx.actor(), metadata={"user_id": user.id})


def grant(db: Session, ctx: AuthContext, user_id: uuid.UUID, role_key: str, reason: str) -> None:
    authorization.require(ctx, "role.assign")
    if user_id == ctx.user_id:
        audit.record_independent("SELF_GRANT_BLOCKED", ctx.actor(), metadata={"role": role_key}, severity="WARNING")
        raise Forbidden("self_grant_forbidden", "Roles cannot be granted to your own account")
    if role_key not in ROLES:
        raise Invalid("unknown_role", "Unknown role")
    if len(reason.strip()) < 5:
        raise Invalid("reason_required", "A reason is required for every role grant")
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("user")
    if role_key in active_role_keys(db, user.id):
        raise Conflict("role_already_granted", "The user already holds this role")
    role = db.execute(select(Role).where(Role.key == role_key)).scalar_one()
    db.add(UserRole(user_id=user.id, role_id=role.id, organization_id=user.organization_id, granted_by=ctx.user_id,
                    reason=reason.strip(), granted_at=clock.now()))
    db.flush()
    event = audit.record(db, "ROLE_GRANTED", ctx.actor(),
                         metadata={"user_id": user.id, "role": role_key, "reason": reason.strip(),
                                   "business_role": role.is_business_role})
    if role.is_business_role:
        db.info.setdefault("alert_events", []).append(event.id)


def revoke(db: Session, ctx: AuthContext, user_id: uuid.UUID, role_key: str) -> None:
    authorization.require(ctx, "role.assign")
    role = db.execute(select(Role).where(Role.key == role_key)).scalar_one_or_none()
    if role is None:
        raise Invalid("unknown_role", "Unknown role")
    grant_row = db.execute(select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id,
                                                  UserRole.revoked_at.is_(None))).scalar_one_or_none()
    if grant_row is None:
        raise NotFound("role grant")
    grant_row.revoked_at = clock.now()
    audit.record(db, "ROLE_REVOKED", ctx.actor(), metadata={"user_id": user_id, "role": role_key})


def roles_catalogue() -> List[dict]:
    return [{"key": k, "names": {"he": v["names"][0], "ar": v["names"][1], "en": v["names"][2]},
             "business": v["business"], "permissions": sorted(v["permissions"])} for k, v in ROLES.items()]


def flush_alerts(db: Session) -> None:
    """Call after commit: notify oversight about events queued in db.info."""
    for event_id in db.info.pop("alert_events", []):
        notifications.alert_oversight(event_id)
