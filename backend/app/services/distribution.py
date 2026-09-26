"""DistributionService — automatic supplier distribution.

Staff choose categories; the system computes recipients. Snapshots are never
edited: late registrants go into a SUPPLEMENTAL snapshot, manual additions into
a MANUAL snapshot.

Whether staff may change the list is the process type's policy
(`ProcessDefinition.distribution_editable`): allowed for quotation requests,
refused for tenders. Every manual change carries a reason, is audited and is
shown in the fairness report and protocol. A removal marks the recipient row
(`removed_at`, `removed_by`, `removal_reason`); it never deletes it.
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
from app.core.errors import Conflict, Forbidden, Invalid, NotFound
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
    manual: Optional[dict] = None  # {"reason", "by"} for a manual addition


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
    reason = {"matches": [
        {"supplier_category_id": m.supplier_category_id, "process_category_id": m.process_category_id,
         "relation": m.relation}
        for m in matched.matches
    ]}
    if matched.manual:
        reason["manual"] = matched.manual
    return reason


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
                    categories: List[Category], extra_rule: Optional[dict] = None) -> DistributionSnapshot:
    rule = {
        "strategy": "manual" if kind == "MANUAL" else "category_match",
        "category_ids": sorted(str(c.id) for c in categories),
        "regions": (process.details or {}).get("service_regions", []),
        "relations": ["exact", "supplier_broader", "supplier_narrower"],
        "supplier_status": "ACTIVE",
    }
    rule.update(extra_rule or {})
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


def _require_editable(process: Process) -> None:
    if not get_definition(process.process_type).distribution_editable:
        raise Forbidden("distribution_not_editable", "The distribution of this process type cannot be changed")


def _require_reason(reason: str) -> str:
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise Invalid("reason_required", "A reason is required for every change to the distribution list")
    return reason


def _active_suppliers(db: Session, ids: Sequence[uuid.UUID]) -> List[Supplier]:
    ids = list(dict.fromkeys(ids))
    found = list(db.execute(select(Supplier).where(Supplier.id.in_(ids))).scalars()) if ids else []
    if len(found) != len(ids) or any(s.status != "ACTIVE" for s in found):
        raise Invalid("invalid_supplier", "Every supplier must exist and be active")
    return found


def _manual(reason: str, actor: Actor) -> dict:
    return {"reason": reason, "by": str(actor.user_id) if actor.user_id else None}


def create_initial_distribution(db: Session, process: Process, actor: Actor,
                                excluded_ids: Sequence[uuid.UUID] = (), additional_ids: Sequence[uuid.UUID] = (),
                                reason: str = "") -> DistributionSnapshot:
    categories = _process_categories(db, process)
    regions = (process.details or {}).get("service_regions", [])
    matched = match_suppliers(db, categories, regions)
    extra_rule = None
    if excluded_ids or additional_ids:
        _require_editable(process)
        reason = _require_reason(reason)
        excluded = set(excluded_ids)
        matched_ids = {m.supplier.id for m in matched}
        if excluded - matched_ids:
            raise Invalid("invalid_supplier", "Only matched suppliers can be excluded")
        removed = [m for m in matched if m.supplier.id in excluded]
        matched = [m for m in matched if m.supplier.id not in excluded]
        for supplier in _active_suppliers(db, [i for i in additional_ids if i not in matched_ids]):
            matched.append(MatchedSupplier(supplier, [], _manual(reason, actor)))
        added = [m for m in matched if m.manual]
        extra_rule = {
            "manual_exclusions": [{"supplier_id": str(m.supplier.id), "company_name": m.supplier.company_name,
                                   "reason": reason} for m in removed],
            "manual_additions": [{"supplier_id": str(m.supplier.id), "company_name": m.supplier.company_name,
                                  "reason": reason} for m in added],
        }
        audit.record(db, "DISTRIBUTION_EDITED", actor, process_id=process.id,
                     metadata={"stage": "publication", "reason": reason,
                               "excluded": sorted(str(m.supplier.id) for m in removed),
                               "added": sorted(str(m.supplier.id) for m in added)})
    return _write_snapshot(db, process, "INITIAL", matched, actor, categories, extra_rule)


def _editable_now(process: Process) -> None:
    _require_editable(process)
    if process.status != "PUBLISHED" or clock.now() >= process.submission_deadline:
        raise Conflict("distribution_closed", "The distribution list can be changed only while submissions are open")


def add_recipient(db: Session, process: Process, supplier_id: uuid.UUID, reason: str,
                  actor: Actor) -> DistributionRecipient:
    _editable_now(process)
    reason = _require_reason(reason)
    supplier = _active_suppliers(db, [supplier_id])[0]
    existing = db.execute(select(DistributionRecipient).where(
        DistributionRecipient.process_id == process.id,
        DistributionRecipient.supplier_id == supplier.id)).scalar_one_or_none()
    if existing is not None and existing.active:
        raise Conflict("already_invited", "This supplier is already on the distribution list")
    if existing is not None:
        existing.removed_at = None
        existing.removed_by = None
        existing.removal_reason = None
        audit.record(db, "DISTRIBUTION_SUPPLIER_RESTORED", actor, process_id=process.id,
                     metadata={"supplier_id": supplier.id, "reason": reason})
        return existing
    categories = _process_categories(db, process)
    regions = (process.details or {}).get("service_regions", [])
    match = next((m for m in match_suppliers(db, categories, regions) if m.supplier.id == supplier.id), None)
    entry = MatchedSupplier(supplier, match.matches if match else [], _manual(reason, actor))
    _write_snapshot(db, process, "MANUAL", [entry], actor, categories,
                    {"manual_additions": [{"supplier_id": str(supplier.id), "company_name": supplier.company_name,
                                           "reason": reason}]})
    audit.record(db, "DISTRIBUTION_SUPPLIER_ADDED", actor, process_id=process.id,
                 metadata={"supplier_id": supplier.id, "reason": reason})
    return db.execute(select(DistributionRecipient).where(
        DistributionRecipient.process_id == process.id,
        DistributionRecipient.supplier_id == supplier.id)).scalar_one()


def remove_recipient(db: Session, process: Process, supplier_id: uuid.UUID, reason: str, actor: Actor) -> None:
    from app.models import Submission

    _editable_now(process)
    reason = _require_reason(reason)
    recipient = db.execute(select(DistributionRecipient).where(
        DistributionRecipient.process_id == process.id,
        DistributionRecipient.supplier_id == supplier_id)).scalar_one_or_none()
    if recipient is None or not recipient.active:
        raise NotFound("recipient")
    submitted = db.execute(select(Submission.id).where(
        Submission.process_id == process.id, Submission.supplier_id == supplier_id,
        Submission.current_version_id.is_not(None))).first()
    if submitted:
        raise Conflict("supplier_already_submitted", "This supplier has already submitted and cannot be removed")
    recipient.removed_at = clock.now()
    recipient.removed_by = actor.user_id
    recipient.removal_reason = reason
    audit.record(db, "DISTRIBUTION_SUPPLIER_REMOVED", actor, process_id=process.id,
                 metadata={"supplier_id": supplier_id, "reason": reason})


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
