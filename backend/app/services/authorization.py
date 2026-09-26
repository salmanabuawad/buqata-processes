"""AuthorizationService — the single place a permission or scope is checked.

Permission: does one of the caller's roles grant it?
Scope: is the caller a participant of this specific process (need-to-know)?
"""
from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.models import DistributionRecipient, Process, ProcessParticipant
from app.services.identity import AuthContext

CONTENT_PARTICIPATIONS = ("OWNER", "TEAM", "COMMITTEE", "OPENING_OFFICIAL", "CONTENT_ACCESS")
MANAGE_PARTICIPATIONS = ("OWNER", "TEAM")


def require(ctx: AuthContext, permission: str) -> None:
    if not ctx.has(permission):
        raise Forbidden("forbidden", f"Missing permission {permission}")


def require_any(ctx: AuthContext, permissions: Iterable[str]) -> None:
    if not any(ctx.has(p) for p in permissions):
        raise Forbidden("forbidden", "Missing permission")


def participation(db: Session, ctx: AuthContext, process: Process) -> set[str]:
    rows = db.execute(
        select(ProcessParticipant.participation).where(
            ProcessParticipant.process_id == process.id,
            ProcessParticipant.user_id == ctx.user_id,
            ProcessParticipant.revoked_at.is_(None),
        )
    ).scalars()
    return set(rows)


def require_scope(
    db: Session,
    ctx: AuthContext,
    process: Process,
    permission: str,
    participations: Iterable[str] = CONTENT_PARTICIPATIONS,
) -> None:
    require(ctx, permission)
    if not participation(db, ctx, process) & set(participations):
        raise Forbidden("not_a_participant", "You are not assigned to this process")


def supplier_recipient(db: Session, ctx: AuthContext, process: Process) -> Optional[DistributionRecipient]:
    if ctx.supplier_id is None:
        return None
    return db.execute(
        select(DistributionRecipient).where(
            DistributionRecipient.process_id == process.id,
            DistributionRecipient.supplier_id == ctx.supplier_id,
        )
    ).scalar_one_or_none()


def can_view_process(db: Session, ctx: AuthContext, process: Process) -> bool:
    if ctx.has("process.read"):
        return True
    return supplier_recipient(db, ctx, process) is not None
