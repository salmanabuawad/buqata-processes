"""MfaService — local TOTP enrolment, sign-in verification and session step-up.

The shared secret is wrapped by the KMS (context bound to the user id) before
it is stored; the database alone never yields a usable secret. Staff signing
in through Entra ID get `mfa` in `amr` from the identity provider instead.
"""
from __future__ import annotations

import base64
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.adapters.kms import get_kms
from app.core import clock, totp
from app.core.errors import Conflict, DomainError
from app.models import AuthSession, User
from app.services import audit
from app.services.audit import Actor
from app.services.identity import AuthContext

ISSUER = "Buqata Processes"


def _context(user: User) -> str:
    return f"totp:{user.id}"


def _store_secret(user: User, secret: bytes) -> None:
    user.totp_secret = base64.b64encode(get_kms().wrap(secret, _context(user))).decode("ascii")


def _load_secret(user: User) -> bytes:
    return get_kms().unwrap(base64.b64decode(user.totp_secret), _context(user))


def is_enrolled(user: User) -> bool:
    return user.totp_enabled_at is not None and bool(user.totp_secret)


def check_code(user: User, code: str) -> bool:
    """Verify a code against the user's secret and consume its time step (no replay)."""
    if not user.totp_secret:
        return False
    step = totp.matching_step(_load_secret(user), code, clock.now().timestamp(), user.totp_last_step)
    if step is None:
        return False
    user.totp_last_step = step
    return True


def _mark_session(db: Session, ctx: AuthContext) -> None:
    session = db.get(AuthSession, ctx.session_id)
    amr = list(session.amr or [])
    if "otp" not in amr:
        session.amr = amr + ["otp"]
    ctx.amr = list(session.amr)


def _refuse(ctx: AuthContext, stage: str) -> DomainError:
    audit.record_independent("MFA_FAILED", ctx.actor(), metadata={"stage": stage})
    return DomainError("invalid_otp", "The verification code is not valid", status_code=401)


def start_enrolment(db: Session, ctx: AuthContext) -> Dict[str, str]:
    user = db.get(User, ctx.user_id)
    if is_enrolled(user):
        raise Conflict("mfa_already_enrolled", "Two-step verification is already enabled")
    secret = totp.new_secret()
    _store_secret(user, secret)
    user.totp_enabled_at = None
    user.totp_last_step = None
    audit.record(db, "MFA_ENROLMENT_STARTED", ctx.actor())
    db.commit()
    # The secret is shown once, to its owner, so an authenticator app can be set up.
    return {"secret": totp.to_base32(secret), "otpauth_uri": totp.provisioning_uri(secret, user.email, ISSUER)}


def confirm_enrolment(db: Session, ctx: AuthContext, code: str) -> None:
    user = db.get(User, ctx.user_id)
    if is_enrolled(user):
        raise Conflict("mfa_already_enrolled", "Two-step verification is already enabled")
    if not user.totp_secret:
        raise Conflict("mfa_not_started", "Start enrolment first")
    if not check_code(user, code):
        db.rollback()
        raise _refuse(ctx, "enrol")
    user.totp_enabled_at = clock.now()
    _mark_session(db, ctx)
    audit.record(db, "MFA_ENABLED", ctx.actor())
    db.commit()


def step_up(db: Session, ctx: AuthContext, code: str) -> None:
    user = db.get(User, ctx.user_id)
    if not is_enrolled(user):
        raise Conflict("mfa_not_enrolled", "Two-step verification is not enabled for this account")
    if not check_code(user, code):
        db.rollback()
        raise _refuse(ctx, "step_up")
    _mark_session(db, ctx)
    audit.record(db, "MFA_STEP_UP", ctx.actor())
    db.commit()


def disable(db: Session, ctx: AuthContext, code: str) -> None:
    user = db.get(User, ctx.user_id)
    if not is_enrolled(user):
        raise Conflict("mfa_not_enrolled", "Two-step verification is not enabled for this account")
    if not check_code(user, code):
        db.rollback()
        raise _refuse(ctx, "disable")
    _clear(user)
    audit.record(db, "MFA_DISABLED", ctx.actor(), metadata={"by": "owner"})
    db.commit()


def reset(db: Session, user: User, actor: Actor, reason: str) -> None:
    """Operator reset for a lost authenticator; the caller commits."""
    _clear(user)
    audit.record(db, "MFA_DISABLED", actor, metadata={"by": "operator", "user_id": user.id, "reason": reason})


def _clear(user: User) -> None:
    user.totp_secret = None
    user.totp_enabled_at = None
    user.totp_last_step = None


def verify_at_login(user: User, code: Optional[str]) -> bool:
    """True when the sign-in may proceed with `otp` in amr; raises when a code is needed or wrong."""
    if not is_enrolled(user):
        return False
    if not code:
        raise DomainError("mfa_required", "Enter the code from your authenticator app", status_code=401)
    if not check_code(user, code):
        raise DomainError("invalid_otp", "The verification code is not valid", status_code=401)
    return True
