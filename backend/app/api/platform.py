"""Notifications, audit trail, dashboards."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_context
from app.core import clock
from app.core.errors import NotFound
from app.db import get_db
from app.models import AuditEvent, Notification, Process, User
from app.services import audit, authorization, reporting
from app.services.identity import AuthContext

router = APIRouter()


@router.get("/notifications", tags=["notifications"])
def my_notifications(limit: int = 30, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    rows = db.execute(select(Notification).where(Notification.recipient_user_id == ctx.user_id)
                      .order_by(Notification.created_at.desc()).limit(min(max(limit, 1), 100))).scalars().all()
    unread = reporting.unread_notifications(db, ctx.user_id)
    return {"unread": unread, "items": [
        {"id": str(n.id), "event_type": n.event_type, "subject": n.subject, "body": n.body, "link": n.link,
         "created_at": n.created_at.isoformat(), "read": n.read_at is not None,
         "process_id": str(n.process_id) if n.process_id else None}
        for n in rows
    ]}


@router.post("/notifications/{notification_id}/read", tags=["notifications"])
def mark_read(notification_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_user_id != ctx.user_id:
        raise NotFound("notification")
    if n.read_at is None:
        n.read_at = clock.now()
        db.commit()
    return {"ok": True}


@router.post("/notifications/read-all", tags=["notifications"])
def mark_all_read(ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    for n in db.execute(select(Notification).where(Notification.recipient_user_id == ctx.user_id,
                                                   Notification.read_at.is_(None))).scalars():
        n.read_at = clock.now()
    db.commit()
    return {"ok": True}


@router.get("/audit/events", tags=["audit"])
def audit_events(process_id: Optional[uuid.UUID] = None, event_type: Optional[str] = None,
                 severity: Optional[str] = None, limit: int = 100, offset: int = 0,
                 ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    authorization.require(ctx, "audit.read")
    stmt = select(AuditEvent)
    if process_id:
        stmt = stmt.where(AuditEvent.process_id == process_id)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if severity:
        stmt = stmt.where(AuditEvent.severity == severity)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(AuditEvent.sequence.desc()).limit(min(max(limit, 1), 500))
                      .offset(max(offset, 0))).scalars().all()
    users = {u.id: u.full_name for u in db.execute(select(User).where(
        User.id.in_([e.actor_id for e in rows if e.actor_id]))).scalars()}
    refs = {p.id: p.reference_number for p in db.execute(select(Process).where(
        Process.id.in_([e.process_id for e in rows if e.process_id]))).scalars()}
    return {"total": total, "items": [
        {"sequence": e.sequence, "event_type": e.event_type, "severity": e.severity,
         "occurred_at": e.occurred_at.isoformat(), "actor": users.get(e.actor_id), "actor_role": e.actor_role,
         "process_id": str(e.process_id) if e.process_id else None, "process_reference": refs.get(e.process_id),
         "submission_id": str(e.submission_id) if e.submission_id else None, "ip": e.ip,
         "metadata": e.metadata_, "previous_hash": e.previous_hash, "event_hash": e.event_hash}
        for e in rows
    ]}


@router.post("/audit/verify", tags=["audit"])
def verify(ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    authorization.require(ctx, "audit.verify")
    report = audit.verify_audit_chain(db)
    audit.record(db, "AUDIT_CHAIN_VERIFIED", ctx.actor(),
                 metadata={"valid": report.valid, "checked": report.checked,
                           "first_broken_sequence": report.first_broken_sequence})
    db.commit()
    return {"valid": report.valid, "checked": report.checked, "first_broken_sequence": report.first_broken_sequence,
            "reason": report.reason, "head_hash": report.head_hash}


@router.get("/dashboard/staff", tags=["dashboard"])
def staff_dashboard(ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    return reporting.staff_dashboard(db, ctx)
