"""AuditService — append-only, hash-chained audit trail.

event_hash = SHA-256(canonical JSON of every field except event_hash).
The canonical form includes previous_hash, so altering, inserting or removing
any earlier event breaks every hash after it. verify_audit_chain() recomputes
the whole chain.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import db as db_module
from app.core import clock
from app.core.security import sha256_hex
from app.models import AuditEvent

log = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64
_ADVISORY_LOCK_KEY = 7_331_001  # arbitrary, constant: serialises chain appends on PostgreSQL

CRITICAL_EVENTS = {
    "EARLY_OPEN_ATTEMPT",
    "UNAUTHORIZED_NETWORK_ATTEMPT",
    "UNAUTHORIZED_DEVICE_ATTEMPT",
    "SEALED_ACCESS_DENIED",
    "FILE_INTEGRITY_FAILURE",
}
WARNING_EVENTS = {"FAILED_MULTI_APPROVAL", "OPENING_REJECTED", "LOGIN_FAILED", "ROLE_GRANTED", "NOTIFICATION_FAILED",
                  "MFA_FAILED", "MFA_DISABLED"}


@dataclass(frozen=True)
class Actor:
    user_id: Optional[uuid.UUID] = None
    role: Optional[str] = None
    ip: Optional[str] = None

    @classmethod
    def system(cls) -> "Actor":
        return cls(None, "system", None)


def _json_default(value: Any):
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, datetime):
        return clock.ensure_utc(value).isoformat()
    raise TypeError(f"Unserialisable audit value: {type(value)!r}")


def canonical_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def _normalise_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    # Round-trip through JSON so the hashed form equals what the database stores.
    return json.loads(canonical_json(metadata or {}))


def compute_event_hash(event: AuditEvent) -> str:
    material = {
        "sequence": event.sequence,
        "event_type": event.event_type,
        "severity": event.severity,
        "occurred_at": clock.ensure_utc(event.occurred_at).isoformat(timespec="microseconds"),
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "actor_role": event.actor_role,
        "process_id": str(event.process_id) if event.process_id else None,
        "submission_id": str(event.submission_id) if event.submission_id else None,
        "ip": event.ip,
        "metadata": event.metadata_,
        "previous_hash": event.previous_hash,
    }
    return sha256_hex(canonical_json(material).encode("utf-8"))


def severity_for(event_type: str) -> str:
    if event_type in CRITICAL_EVENTS:
        return "CRITICAL"
    if event_type in WARNING_EVENTS:
        return "WARNING"
    return "INFO"


def record(
    db: Session,
    event_type: str,
    actor: Actor,
    *,
    process_id: Optional[uuid.UUID] = None,
    submission_id: Optional[uuid.UUID] = None,
    metadata: Optional[Dict[str, Any]] = None,
    severity: Optional[str] = None,
) -> AuditEvent:
    """Append an event inside the caller's transaction. If the caller rolls
    back, the event goes with it — no action without its audit record."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
    last = db.execute(
        select(AuditEvent.sequence, AuditEvent.event_hash).order_by(AuditEvent.sequence.desc()).limit(1)
    ).first()
    sequence = (last[0] + 1) if last else 1
    previous_hash = last[1] if last else GENESIS_HASH
    occurred_at = clock.now()
    event = AuditEvent(
        id=uuid.uuid4(),
        sequence=sequence,
        event_type=event_type,
        severity=severity or severity_for(event_type),
        occurred_at=occurred_at,
        actor_id=actor.user_id,
        actor_role=actor.role,
        process_id=process_id,
        submission_id=submission_id,
        ip=actor.ip,
        metadata_=_normalise_metadata(metadata),
        previous_hash=previous_hash,
    )
    event.event_hash = compute_event_hash(event)
    db.add(event)
    db.flush()
    return event


def record_independent(event_type: str, actor: Actor, **kwargs) -> None:
    """Record in its own transaction — for denials, where the caller's
    transaction is about to fail but the attempt itself must be kept."""
    session = db_module.SessionLocal()
    try:
        event = record(session, event_type, actor, **kwargs)
        session.commit()
        if event.severity == "CRITICAL":
            from app.services import notifications

            notifications.alert_oversight(event.id)
    except Exception:  # pragma: no cover - logged, never masks the original denial
        session.rollback()
        log.exception("Could not record independent audit event %s", event_type)
    finally:
        session.close()


def head_hash(db: Session) -> str:
    last = db.execute(select(AuditEvent.event_hash).order_by(AuditEvent.sequence.desc()).limit(1)).scalar()
    return last or GENESIS_HASH


@dataclass
class ChainReport:
    valid: bool
    checked: int
    first_broken_sequence: Optional[int]
    reason: Optional[str]
    head_hash: str


def verify_audit_chain(db: Session, batch_size: int = 1000) -> ChainReport:
    expected_previous = GENESIS_HASH
    expected_sequence = 1
    checked = 0
    offset = 0
    while True:
        batch = db.execute(
            select(AuditEvent)
            .order_by(AuditEvent.sequence)
            .offset(offset)
            .limit(batch_size)
            .execution_options(populate_existing=True)
        ).scalars().all()
        if not batch:
            break
        for event in batch:
            if event.sequence != expected_sequence:
                return ChainReport(False, checked, event.sequence, "sequence_gap", expected_previous)
            if event.previous_hash != expected_previous:
                return ChainReport(False, checked, event.sequence, "previous_hash_mismatch", expected_previous)
            if compute_event_hash(event) != event.event_hash:
                return ChainReport(False, checked, event.sequence, "event_hash_mismatch", expected_previous)
            expected_previous = event.event_hash
            expected_sequence += 1
            checked += 1
        offset += batch_size
    return ChainReport(True, checked, None, None, expected_previous)


def count_events(db: Session, **filters) -> int:
    stmt = select(func.count(AuditEvent.id))
    for key, value in filters.items():
        stmt = stmt.where(getattr(AuditEvent, key) == value)
    return db.execute(stmt).scalar_one()
