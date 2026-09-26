"""ReportingService — fairness report and dashboards.

Every number here is *measured* from records. Estimated figures (staff hours
saved, etc.) belong to the KPI module and are labelled as estimates there.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.models import (
    AuditEvent,
    DistributionRecipient,
    DistributionSnapshot,
    Notification,
    NotificationDelivery,
    OpeningPolicyRecord,
    OpeningRequest,
    Process,
    ProcessParticipant,
    Submission,
    Supplier,
    SupplierDocument,
    User,
)
from app.services import authorization, distribution as distribution_service, processes as process_service
from app.services.identity import AuthContext


def fairness(db: Session, ctx: AuthContext, process: Process, locale: str = "he") -> dict:
    authorization.require(ctx, "process.monitor")
    recipients = distribution_service.recipients(db, process.id)
    snapshots = db.execute(select(DistributionSnapshot).where(DistributionSnapshot.process_id == process.id)
                           .order_by(DistributionSnapshot.created_at)).scalars().all()
    notification_ids = [r.notification_id for r in recipients if r.notification_id]
    deliveries: Dict = {}
    if notification_ids:
        for d in db.execute(select(NotificationDelivery).where(
                NotificationDelivery.notification_id.in_(notification_ids),
                NotificationDelivery.channel == "EMAIL")).scalars():
            deliveries[d.notification_id] = d
    submitted_suppliers = {s.supplier_id for s in process_service.submitted(db, process)}
    vault_row = process_service.vault_of(db, process)
    revealed = vault_row is None or vault_row.status == "OPENED"

    category_ids = sorted({m["process_category_id"] for r in recipients for m in r.match_reason.get("matches", [])}
                          | {m["supplier_category_id"] for r in recipients for m in r.match_reason.get("matches", [])})
    names = distribution_service.category_names(db, category_ids, locale)

    rows = []
    stats = {"eligible": len(recipients), "notifications": 0, "delivered": 0, "failed": 0, "pending": 0,
             "opened": 0, "started": 0, "submitted": len(submitted_suppliers)}
    for r in recipients:
        delivery = deliveries.get(r.notification_id)
        status = delivery.status if delivery else ("NO_EMAIL" if r.notification_id else "NONE")
        if r.notification_id:
            stats["notifications"] += 1
        if status == "SENT":
            stats["delivered"] += 1
        elif status in ("FAILED", "DEAD"):
            stats["failed"] += 1
        elif status == "PENDING":
            stats["pending"] += 1
        if r.opened_at:
            stats["opened"] += 1
        if r.submission_started_at:
            stats["started"] += 1
        rows.append({
            "supplier_id": str(r.supplier_id),
            "supplier_name": r.supplier.company_name,
            "city": r.supplier.city,
            "snapshot_kind": next((s.kind for s in snapshots if s.id == r.snapshot_id), None),
            "match": [
                {"relation": m["relation"], "supplier_category": names.get(m["supplier_category_id"]),
                 "process_category": names.get(m["process_category_id"])}
                for m in r.match_reason.get("matches", [])
            ],
            "notified_at": r.notified_at.isoformat(),
            "delivery_status": status,
            "opened_at": r.opened_at.isoformat() if r.opened_at else None,
            "started": r.submission_started_at is not None,
            # Who submitted is withheld until the vault is opened.
            "submitted": (r.supplier_id in submitted_suppliers) if revealed else None,
        })
    return {
        "process_id": str(process.id),
        "reference_number": process.reference_number,
        "stats": stats,
        "submitted_revealed": revealed,
        "snapshots": [{"id": str(s.id), "kind": s.kind, "created_at": s.created_at.isoformat(),
                       "recipient_count": s.recipient_count, "snapshot_hash": s.snapshot_hash, "rule": s.rule}
                      for s in snapshots],
        "recipients": rows,
        "manual_changes_possible": False,
    }


def staff_dashboard(db: Session, ctx: AuthContext) -> dict:
    authorization.require(ctx, "process.read")
    now = clock.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def count_processes(ptype: str, *conds):
        return db.execute(select(func.count(Process.id)).where(Process.process_type == ptype, *conds)).scalar_one()

    active_rfq = count_processes("rfq", Process.status == "PUBLISHED", Process.submission_deadline > now)
    waiting_opening = db.execute(select(func.count(Process.id)).where(
        Process.status == "PUBLISHED", Process.submission_deadline <= now)).scalar_one()
    my_pending = db.execute(select(func.count(OpeningRequest.id)).where(OpeningRequest.status == "PENDING")).scalar_one() \
        if ctx.has("opening.approve") else 0
    submissions_today = db.execute(select(func.count(Submission.id)).where(
        Submission.submitted_at >= start_of_day)).scalar_one()
    suppliers_active = db.execute(select(func.count(Supplier.id)).where(Supplier.status == "ACTIVE")).scalar_one()
    expiring = db.execute(select(func.count(SupplierDocument.id)).where(
        SupplierDocument.expires_on.is_not(None),
        SupplierDocument.expires_on <= (now + timedelta(days=30)).date())).scalar_one()
    alerts_since = now - timedelta(days=30)
    security_alerts = db.execute(select(func.count(AuditEvent.id)).where(
        AuditEvent.severity == "CRITICAL", AuditEvent.occurred_at >= alerts_since)).scalar_one()

    by_status = dict(db.execute(select(Process.status, func.count()).group_by(Process.status)).all())
    by_type = dict(db.execute(select(Process.process_type, func.count()).group_by(Process.process_type)).all())

    # Participation: suppliers reached and submissions per published RFQ.
    published = db.execute(select(Process).where(Process.published_at.is_not(None), Process.process_type == "rfq")
                           .order_by(Process.published_at)).scalars().all()
    participation = []
    for p in published[-12:]:
        c = process_service.counts(db, p)
        participation.append({"reference": p.reference_number, "invited": c["recipients"],
                              "submitted": c["submissions"] if p.status != "PUBLISHED" else None})
    reached = [x["invited"] for x in participation]
    received = [x["submitted"] for x in participation if x["submitted"] is not None]

    delivery = dict(db.execute(select(NotificationDelivery.status, func.count())
                               .where(NotificationDelivery.channel == "EMAIL")
                               .group_by(NotificationDelivery.status)).all())

    recent = db.execute(select(AuditEvent).where(AuditEvent.event_type.in_((
        "PROCESS_PUBLISHED", "SUPPLIERS_MATCHED", "SUBMISSION_SEALED", "VAULT_OPENED", "DECISION_RECORDED",
        "PROTOCOL_GENERATED", "SUPPLIER_REGISTERED", "EARLY_OPEN_ATTEMPT", "FILE_INTEGRITY_FAILURE",
        "SEALED_ACCESS_DENIED", "PROCESS_CREATED",
    ))).order_by(AuditEvent.sequence.desc()).limit(12)).scalars().all()
    process_refs = {p.id: p.reference_number for p in db.execute(
        select(Process).where(Process.id.in_([e.process_id for e in recent if e.process_id]))).scalars()}
    actor_names = {u.id: u.full_name for u in db.execute(
        select(User).where(User.id.in_([e.actor_id for e in recent if e.actor_id]))).scalars()}

    return {
        "cards": {
            "active_rfqs": active_rfq,
            "active_tenders": count_processes("tender", Process.status == "PUBLISHED"),
            "active_scholarships": count_processes("scholarship", Process.status == "PUBLISHED"),
            "waiting_for_opening": waiting_opening,
            "waiting_for_my_approval": my_pending,
            "submissions_today": submissions_today,
            "registered_suppliers": suppliers_active,
            "expiring_supplier_documents": expiring,
            "security_alerts_30d": security_alerts,
        },
        "processes_by_status": by_status,
        "processes_by_type": by_type,
        "participation": participation,
        "average_suppliers_reached": round(sum(reached) / len(reached), 1) if reached else None,
        "average_quotations_received": round(sum(received) / len(received), 1) if received else None,
        "email_delivery": delivery,
        "recent_activity": [
            {"sequence": e.sequence, "event_type": e.event_type, "severity": e.severity,
             "occurred_at": e.occurred_at.isoformat(), "process_reference": process_refs.get(e.process_id),
             "process_id": str(e.process_id) if e.process_id else None,
             "actor": actor_names.get(e.actor_id) or e.actor_role}
            for e in recent
        ],
    }


def supplier_opportunities(db: Session, ctx: AuthContext) -> List[dict]:
    authorization.require(ctx, "supplier.self")
    if ctx.supplier_id is None:
        return []
    rows = db.execute(
        select(DistributionRecipient, Process).join(Process, Process.id == DistributionRecipient.process_id)
        .where(DistributionRecipient.supplier_id == ctx.supplier_id)
        .order_by(Process.submission_deadline.desc())
    ).all()
    subs = {s.process_id: s for s in db.execute(select(Submission).where(
        Submission.supplier_id == ctx.supplier_id)).scalars()}
    result = []
    for recipient, process in rows:
        s = subs.get(process.id)
        result.append({
            "process_id": str(process.id), "reference_number": process.reference_number, "title": process.title,
            "process_type": process.process_type, "status": process.status,
            "phase": process_service.phase(process), "deadline": process.submission_deadline.isoformat(),
            "invited_at": recipient.notified_at.isoformat(), "opened_at": recipient.opened_at.isoformat() if recipient.opened_at else None,
            "submission_status": s.status if s else None,
            "submitted_at": s.submitted_at.isoformat() if s and s.submitted_at else None,
        })
    return result


def participants(db: Session, process: Process) -> List[dict]:
    rows = db.execute(select(ProcessParticipant, User).join(User, User.id == ProcessParticipant.user_id)
                      .where(ProcessParticipant.process_id == process.id, ProcessParticipant.revoked_at.is_(None))).all()
    return [{"user_id": str(u.id), "name": u.full_name, "participation": p.participation} for p, u in rows]


def opening_policy_summary(db: Session, process: Process) -> dict:
    record = db.execute(select(OpeningPolicyRecord).where(OpeningPolicyRecord.process_id == process.id)).scalar_one()
    return {"rules": record.rules, "required_approvals": record.required_approvals, "frozen": record.frozen}


def unread_notifications(db: Session, user_id) -> int:
    return db.execute(select(func.count(Notification.id)).where(
        Notification.recipient_user_id == user_id, Notification.read_at.is_(None))).scalar_one()
