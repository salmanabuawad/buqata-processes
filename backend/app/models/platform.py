"""Notifications (outbox) and the audit trail."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONType, UTCDateTime
from app.models.base import created_at_column, uuid_pk


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    recipient_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("suppliers.id"))
    recipient_email: Mapped[Optional[str]] = mapped_column(String(254))
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    locale: Mapped[str] = mapped_column(String(5))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[Optional[str]] = mapped_column(String(500))
    process_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("processes.id"), index=True)
    created_at: Mapped[datetime] = created_at_column()
    read_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    deliveries: Mapped[List["NotificationDelivery"]] = relationship(
        back_populates="notification", cascade="all, delete-orphan"
    )


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = uuid_pk()
    notification_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notifications.id"), index=True)
    channel: Mapped[str] = mapped_column(String(20))  # EMAIL | IN_APP | SMS | WHATSAPP
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, index=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    sent_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    notification: Mapped[Notification] = relationship(back_populates="deliveries")


class AuditEvent(Base):
    """Append-only, hash-chained. No foreign keys on purpose: the log must never
    block a write elsewhere or disappear through a cascade."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    sequence: Mapped[int] = mapped_column(BigInteger, unique=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    severity: Mapped[str] = mapped_column(String(10), default="INFO", index=True)
    occurred_at: Mapped[datetime] = created_at_column()
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    actor_role: Mapped[Optional[str]] = mapped_column(String(64))
    process_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, index=True)
    submission_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    previous_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)
