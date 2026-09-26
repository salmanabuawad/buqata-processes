from __future__ import annotations

import hmac
import ipaddress
from typing import Optional

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import Forbidden, NotAuthenticated
from app.db import get_db
from app.services import identity
from app.services.identity import AuthContext

SESSION_COOKIE = "bdp_session"
CSRF_COOKIE = "bdp_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def client_ip(request: Request) -> Optional[str]:
    peer = request.client.host if request.client else None
    settings = get_settings()
    if peer and peer in settings.trusted_proxies:
        forwarded = request.headers.get("x-real-ip") or (request.headers.get("x-forwarded-for") or "").split(",")[0]
        forwarded = forwarded.strip()
        if forwarded:
            try:
                ipaddress.ip_address(forwarded)
                return forwarded
            except ValueError:
                pass
    return peer


def current_context(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    ctx = identity.resolve(db, request.cookies.get(SESSION_COOKIE), client_ip(request))
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token") or ""
        expected = identity.csrf_for(db, ctx.session_id)
        if not sent or not hmac.compare_digest(sent, expected):
            raise Forbidden("csrf_failed", "Missing or invalid CSRF token")
    return ctx


def optional_context(request: Request, db: Session = Depends(get_db)) -> Optional[AuthContext]:
    try:
        return identity.resolve(db, request.cookies.get(SESSION_COOKIE), client_ip(request))
    except NotAuthenticated:
        return None


def set_session_cookies(response: Response, token: str, csrf: str) -> None:
    settings = get_settings()
    max_age = settings.session_absolute_hours * 3600
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite="lax",
                        max_age=max_age, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=settings.cookie_secure, samesite="lax",
                        max_age=max_age, path="/")


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
