"""NotificationService — transactional outbox.

`enqueue` writes notification + delivery rows inside the caller's transaction
(under a savepoint: a template or data error is logged and swallowed, it never
aborts the business action). The worker delivers e-mail after commit, retries
with backoff, and records every outcome. A delivery failure therefore can never
roll back the publication or submission that caused it.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import event, or_, select
from sqlalchemy.orm import Session

from app import db as db_module
from app.adapters.mail import get_mail_transport
from app.config import get_settings
from app.core import clock
from app.core.rbac import ROLES
from app.models import AuditEvent, Notification, NotificationDelivery, Process, Role, User, UserRole
from app.services import audit
from app.services.audit import Actor
from app.services.notification_templates import render

log = logging.getLogger(__name__)

RETRY_SCHEDULE_MINUTES = [1, 5, 15, 60]
MAX_ATTEMPTS = len(RETRY_SCHEDULE_MINUTES) + 1


@dataclass
class Recipient:
    user_id: Optional[uuid.UUID]
    email: Optional[str]
    locale: str = "he"
    supplier_id: Optional[uuid.UUID] = None
    email_enabled: bool = True
    in_app_enabled: bool = True


def local_time(value: datetime) -> datetime:
    return clock.ensure_utc(value).astimezone(ZoneInfo(get_settings().timezone))


def format_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return "—"
    return local_time(value).strftime("%d.%m.%Y %H:%M")


def enqueue(
    db: Session,
    event_type: str,
    recipients: Iterable[Recipient],
    params: dict,
    *,
    process_id: Optional[uuid.UUID] = None,
    link: Optional[str] = None,
    per_recipient_params=None,
) -> List[Notification]:
    created: List[Notification] = []
    for recipient in recipients:
        try:
            with db.begin_nested():
                merged = dict(params)
                if per_recipient_params:
                    merged.update(per_recipient_params(recipient))
                subject, body = render(event_type, recipient.locale, merged)
                notification = Notification(
                    recipient_user_id=recipient.user_id,
                    recipient_supplier_id=recipient.supplier_id,
                    recipient_email=recipient.email,
                    event_type=event_type,
                    locale=recipient.locale,
                    subject=subject,
                    body=body,
                    link=merged.get("link", link),
                    process_id=process_id,
                )
                if recipient.user_id and recipient.in_app_enabled:
                    notification.deliveries.append(
                        NotificationDelivery(channel="IN_APP", status="SENT", attempts=1, sent_at=clock.now())
                    )
                if recipient.email and recipient.email_enabled:
                    notification.deliveries.append(
                        NotificationDelivery(channel="EMAIL", status="PENDING", next_attempt_at=clock.now())
                    )
                db.add(notification)
                db.flush()
                created.append(notification)
        except Exception:
            log.exception("Could not enqueue %s notification", event_type)
    if created:
        db.info["wake_worker"] = True
    return created


@event.listens_for(Session, "after_commit")
def _wake_worker(session: Session) -> None:
    if not session.info.pop("wake_worker", False):
        return
    url = get_settings().redis_url
    if not url:
        return
    try:
        import redis

        redis.Redis.from_url(url, socket_timeout=1).lpush("bdp:notifications:wake", "1")
    except Exception:  # pragma: no cover - the worker polls anyway
        log.warning("Redis wake-up failed; worker will pick the delivery up on its next poll")


def deliver_pending(db: Session, limit: int = 100) -> dict:
    """Deliver due e-mail. Each delivery is committed on its own."""
    now = clock.now()
    due = db.execute(
        select(NotificationDelivery.id)
        .where(
            NotificationDelivery.channel == "EMAIL",
            NotificationDelivery.status.in_(("PENDING", "FAILED")),
            or_(NotificationDelivery.next_attempt_at.is_(None), NotificationDelivery.next_attempt_at <= now),
        )
        .order_by(NotificationDelivery.next_attempt_at)
        .limit(limit)
    ).scalars().all()
    stats = {"sent": 0, "failed": 0, "dead": 0}
    transport = get_mail_transport()
    for delivery_id in due:
        delivery = db.get(NotificationDelivery, delivery_id)
        notification = delivery.notification
        delivery.attempts += 1
        try:
            transport.send(notification.recipient_email, notification.subject, notification.body)
        except Exception as exc:  # noqa: BLE001 - any transport failure is recorded
            delivery.last_error = str(exc)[:500]
            if delivery.attempts >= MAX_ATTEMPTS:
                delivery.status = "DEAD"
                delivery.next_attempt_at = None
                stats["dead"] += 1
            else:
                delivery.status = "FAILED"
                delivery.next_attempt_at = clock.now() + timedelta(
                    minutes=RETRY_SCHEDULE_MINUTES[delivery.attempts - 1]
                )
                stats["failed"] += 1
            audit.record(
                db, "NOTIFICATION_FAILED", Actor.system(), process_id=notification.process_id,
                metadata={"notification_id": notification.id, "channel": "EMAIL",
                          "event": notification.event_type, "attempt": delivery.attempts, "final": delivery.status == "DEAD"},
            )
        else:
            delivery.status = "SENT"
            delivery.sent_at = clock.now()
            delivery.last_error = None
            delivery.next_attempt_at = None
            stats["sent"] += 1
            audit.record(
                db, "NOTIFICATION_SENT", Actor.system(), process_id=notification.process_id,
                metadata={"notification_id": notification.id, "channel": "EMAIL", "event": notification.event_type},
            )
        db.commit()
    return stats


def recipient_for_user(user: User) -> Recipient:
    return Recipient(user_id=user.id, email=user.email, locale=user.locale or "he")


def oversight_users(db: Session) -> List[User]:
    keys = [key for key, role in ROLES.items() if "security_alert.receive" in role["permissions"]]
    return list(
        db.execute(
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.key.in_(keys), UserRole.revoked_at.is_(None), User.is_active.is_(True))
            .distinct()
        ).scalars()
    )


def alert_oversight(event_id: uuid.UUID) -> None:
    """Notify security-alert holders about a recorded event (own transaction)."""
    session = db_module.SessionLocal()
    try:
        event_row = session.get(AuditEvent, event_id)
        if event_row is None:
            return
        reference = "—"
        if event_row.process_id:
            process = session.get(Process, event_row.process_id)
            reference = process.reference_number if process else "—"
        actor = session.get(User, event_row.actor_id) if event_row.actor_id else None
        enqueue(
            session,
            "SECURITY_ALERT",
            [recipient_for_user(u) for u in oversight_users(session)],
            {
                "event_type": event_row.event_type,
                "reference": reference,
                "occurred_at": format_datetime(event_row.occurred_at),
                "actor": actor.full_name if actor else "system",
                "sequence": event_row.sequence,
            },
            process_id=event_row.process_id,
            link="/audit/",
        )
        session.commit()
    except Exception:  # pragma: no cover
        session.rollback()
        log.exception("Could not alert oversight for audit event %s", event_id)
    finally:
        session.close()
