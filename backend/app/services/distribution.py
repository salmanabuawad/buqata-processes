"""DistributionService — automatic, non-editable supplier distribution.

Municipal staff choose categories; the system chooses recipients. Nothing in
this module accepts an inclusion or exclusion list, and no function edits or
deletes recipients once written: supplements go into a new SUPPLEMENTAL
snapshot.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.core import clock
from app.core.security import new_token, sha256_hex, token_hash
from app.engines.matching import CategoryRef, Match, match_supplier
from app.models import (
    Category,
    DistributionRecipient,
    DistributionSnapshot,
    Process,
    ProcessCategory,
    Supplier,
    SupplierCategory,
    SupplierContact,
    User,
)
from app.processes.registry import get_definition
from app.services import audit, notifications
from app.services.audit import Actor
from app.services.notification_templates import PROCESS_KIND


@dataclass
class MatchedSupplier:
    supplier: Supplier
    matches: List[Match]


def _refs(categories: Sequence[Category]) -> List[CategoryRef]:
    return [CategoryRef(str(c.id), c.path) for c in categories]


def match_suppliers(db: Session, categories: Sequence[Category], regions: Sequence[str] = ()) -> List[MatchedSupplier]:
    process_refs = _refs(categories)
    if not process_refs:
        return []
    suppliers = db.execute(
        select(Supplier)
        .where(Supplier.status == "ACTIVE")
        .options(selectinload(Supplier.categories).selectinload(SupplierCategory.category))
        .order_by(Supplier.company_name)
    ).scalars().all()
    result = []
    for supplier in suppliers:
        supplier_refs = _refs([sc.category for sc in supplier.categories if sc.category.is_active])
        found = match_supplier(supplier_refs, process_refs, supplier.service_regions or [], regions)
        if found:
            result.append(MatchedSupplier(supplier, found))
    return result


def _reason(matched: MatchedSupplier) -> dict:
    return {"matches": [
        {"supplier_category_id": m.supplier_category_id, "process_category_id": m.process_category_id,
         "relation": m.relation}
        for m in matched.matches
    ]}


def _snapshot_hash(process_id: uuid.UUID, kind: str, rows: List[dict]) -> str:
    material = json.dumps({"process": str(process_id), "kind": kind,
                           "recipients": sorted(rows, key=lambda r: r["supplier_id"])},
                          sort_keys=True, separators=(",", ":"))
    return sha256_hex(material.encode())


def _process_categories(db: Session, process: Process) -> List[Category]:
    return list(db.execute(
        select(Category).join(ProcessCategory, ProcessCategory.category_id == Category.id)
        .where(ProcessCategory.process_id == process.id)
    ).scalars())


def _supplier_user(db: Session, supplier: Supplier) -> Optional[User]:
    return db.execute(
        select(User).join(SupplierContact, SupplierContact.user_id == User.id)
        .where(SupplierContact.supplier_id == supplier.id)
        .order_by(SupplierContact.is_primary.desc())
        .limit(1)
    ).scalar_one_or_none()


def _write_snapshot(db: Session, process: Process, kind: str, matched: List[MatchedSupplier], actor: Actor,
                    categories: List[Category]) -> DistributionSnapshot:
    rule = {
        "strategy": "category_match",
        "category_ids": sorted(str(c.id) for c in categories),
        "regions": (process.details or {}).get("service_regions", []),
        "relations": ["exact", "supplier_broader", "supplier_narrower"],
        "supplier_status": "ACTIVE",
    }
    rows = [{"supplier_id": str(m.supplier.id), "reason": _reason(m)} for m in matched]
    snapshot = DistributionSnapshot(
        id=uuid.uuid4(), process_id=process.id, kind=kind, rule=rule, recipient_count=len(matched),
        snapshot_hash=_snapshot_hash(process.id, kind, rows), created_by=actor.user_id, created_at=clock.now(),
    )
    db.add(snapshot)
    db.flush()

    base_url = get_settings().public_base_url.rstrip("/")
    for m in matched:
        token = new_token(24)
        recipient = DistributionRecipient(
            id=uuid.uuid4(), snapshot_id=snapshot.id, process_id=process.id, supplier_id=m.supplier.id,
            match_reason=_reason(m), invitation_token_hash=token_hash(token), notified_at=clock.now(),
        )
        db.add(recipient)
        db.flush()
        user = _supplier_user(db, m.supplier)
        locale = m.supplier.preferred_locale or "he"
        created = notifications.enqueue(
            db,
            "RFQ_INVITATION",
            [notifications.Recipient(
                user_id=user.id if user else None, email=m.supplier.email, locale=locale,
                supplier_id=m.supplier.id, email_enabled=m.supplier.notify_email,
                in_app_enabled=m.supplier.notify_in_app,
            )],
            {
                "company": m.supplier.company_name,
                "reference": process.reference_number,
                "title": process.title,
                "deadline": notifications.format_datetime(process.submission_deadline),
                "link": f"{base_url}/invite/?token={token}",
                "kind": PROCESS_KIND.get(process.process_type, {}).get(locale, ""),
            },
            process_id=process.id,
        )
        if created:
            recipient.notification_id = created[0].id

    audit.record(
        db, "SUPPLIERS_MATCHED", actor, process_id=process.id,
        metadata={"snapshot_id": snapshot.id, "kind": kind, "recipient_count": len(matched),
                  "snapshot_hash": snapshot.snapshot_hash, "rule": rule},
    )
    audit.record(
        db, "NOTIFICATIONS_QUEUED", actor, process_id=process.id,
        metadata={"snapshot_id": snapshot.id, "event": "RFQ_INVITATION", "count": len(matched)},
    )
    return snapshot


def create_initial_distribution(db: Session, process: Process, actor: Actor) -> DistributionSnapshot:
    categories = _process_categories(db, process)
    regions = (process.details or {}).get("service_regions", [])
    matched = match_suppliers(db, categories, regions)
    return _write_snapshot(db, process, "INITIAL", matched, actor, categories)


def extend_for_supplier(db: Session, supplier: Supplier, actor: Actor) -> int:
    """Invite a newly registered / newly categorised supplier to every open
    category-matched process it now matches. Returns the number of invitations."""
    if supplier.status != "ACTIVE":
        return 0
    now = clock.now()
    open_processes = db.execute(
        select(Process).where(Process.status == "PUBLISHED", Process.submission_deadline > now)
    ).scalars().all()
    invited = 0
    for process in open_processes:
        if get_definition(process.process_type).distribution != "category_match":
            continue
        already = db.execute(
            select(DistributionRecipient.id).where(
                DistributionRecipient.process_id == process.id, DistributionRecipient.supplier_id == supplier.id
            )
        ).first()
        if already:
            continue
        categories = _process_categories(db, process)
        regions = (process.details or {}).get("service_regions", [])
        match = next((m for m in match_suppliers(db, categories, regions) if m.supplier.id == supplier.id), None)
        if match:
            _write_snapshot(db, process, "SUPPLEMENTAL", [match], actor, categories)
            invited += 1
    return invited


def preview(db: Session, category_ids: List[uuid.UUID], regions: Sequence[str] = ()) -> List[MatchedSupplier]:
    from app.services.categories import get_many

    return match_suppliers(db, get_many(db, category_ids), regions)


def recipients(db: Session, process_id: uuid.UUID) -> List[DistributionRecipient]:
    return list(db.execute(
        select(DistributionRecipient).where(DistributionRecipient.process_id == process_id)
        .options(selectinload(DistributionRecipient.supplier))
    ).scalars())


def recipient_by_token(db: Session, token: str) -> Optional[DistributionRecipient]:
    return db.execute(
        select(DistributionRecipient).where(DistributionRecipient.invitation_token_hash == token_hash(token))
    ).scalar_one_or_none()


def category_names(db: Session, ids: Sequence[str], locale: str) -> Dict[str, str]:
    if not ids:
        return {}
    rows = db.execute(select(Category).where(Category.id.in_([uuid.UUID(i) for i in ids]))).scalars()
    return {str(c.id): c.name(locale) for c in rows}
