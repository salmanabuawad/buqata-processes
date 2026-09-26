from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, clear_session_cookies, current_context, set_session_cookies
from app.api.schemas import DemoLoginBody, LoginBody, MeUpdate
from app.config import get_settings
from app.core.errors import DomainError, NotFound
from app.db import get_db
from app.models import Supplier, SupplierContact, User
from app.services import audit, identity, reporting
from app.services.identity import AuthContext, active_role_keys

router = APIRouter(tags=["auth"])

# Small in-process limiter; nginx applies the real per-IP limit in deployment.
_attempts: dict = defaultdict(deque)
_WINDOW, _MAX = 300, 10


def _rate_limit(ip: str) -> deque:
    """Refuse when an address has too many recent *failed* sign-ins."""
    now = time.monotonic()
    bucket = _attempts[ip or "?"]
    while bucket and now - bucket[0] > _WINDOW:
        bucket.popleft()
    if len(bucket) >= _MAX:
        raise DomainError("rate_limited", "Too many sign-in attempts; try again in a few minutes", status_code=429)
    return bucket


def me_view(db: Session, ctx: AuthContext) -> dict:
    supplier = db.get(Supplier, ctx.supplier_id) if ctx.supplier_id else None
    return {
        "id": str(ctx.user.id), "email": ctx.user.email, "full_name": ctx.user.full_name, "kind": ctx.user.kind,
        "locale": ctx.user.locale, "roles": sorted(ctx.role_keys), "permissions": sorted(ctx.permissions),
        "mfa": ctx.mfa, "supplier": {"id": str(supplier.id), "company_name": supplier.company_name} if supplier else None,
        "unread_notifications": reporting.unread_notifications(db, ctx.user_id),
    }


@router.post("/auth/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    failures = _rate_limit(ip)
    try:
        token, csrf, user = identity.login(db, body.email, body.password, ip, request.headers.get("user-agent"))
    except DomainError:
        failures.append(time.monotonic())
        raise
    set_session_cookies(response, token, csrf)
    return {"ok": True, "csrf_token": csrf}


@router.post("/auth/logout")
def logout(response: Response, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    identity.logout(db, ctx)
    clear_session_cookies(response)
    return {"ok": True}


@router.get("/auth/me")
def me(ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    return me_view(db, ctx)


@router.patch("/me")
def update_me(body: MeUpdate, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    user = db.get(User, ctx.user_id)
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(user, key, value)
    if changes:
        audit.record(db, "USER_PROFILE_UPDATED", ctx.actor(), metadata={"fields": sorted(changes)})
    db.commit()
    return me_view(db, ctx)


@router.get("/auth/demo-users")
def demo_users(db: Session = Depends(get_db)):
    if not get_settings().demo_enabled:
        raise NotFound()
    users = db.execute(select(User).where(User.is_active.is_(True)).order_by(User.kind, User.full_name)).scalars().all()
    companies = dict(db.execute(select(SupplierContact.user_id, Supplier.company_name)
                                .join(Supplier, Supplier.id == SupplierContact.supplier_id)).all())
    result = []
    for u in users:
        roles = sorted(active_role_keys(db, u.id))
        if u.kind == "supplier" and len([r for r in result if r["kind"] == "supplier"]) >= 6:
            continue
        result.append({"id": str(u.id), "full_name": u.full_name, "kind": u.kind, "roles": roles,
                       "company": companies.get(u.id)})
    return result


@router.post("/auth/demo-login")
def demo_login(body: DemoLoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    token, csrf, _ = identity.demo_login(db, body.user_id, client_ip(request), request.headers.get("user-agent"))
    set_session_cookies(response, token, csrf)
    return {"ok": True, "csrf_token": csrf}
