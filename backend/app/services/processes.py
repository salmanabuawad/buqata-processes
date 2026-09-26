"""ProcessService + WorkflowService: lifecycle of any process type."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import Conflict, Invalid, NotFound
from app.core.security import sha256_hex
from app.models import (
    Decision,
    DistributionRecipient,
    DistributionSnapshot,
    OpeningPolicyRecord,
    Process,
    ProcessCategory,
    ProcessDocument,
    ProcessParticipant,
    ProcessVersion,
    Submission,
    Vault,
)
from app.processes.registry import get_definition
from app.services import audit, authorization, categories as category_service, distribution, documents, vault as vault_service
from app.services.identity import AuthContext
from app.services.suppliers import default_organization

TRANSITIONS: Dict[str, set] = {
    "DRAFT": {"PUBLISHED", "CANCELLED"},
    "PUBLISHED": {"OPENED", "CANCELLED"},
    "OPENED": {"DECIDED"},
    "DECIDED": {"CLOSED"},
    "CLOSED": set(),
    "CANCELLED": set(),
}


def transition(process: Process, target: str) -> None:
    if target not in TRANSITIONS.get(process.status, set()):
        raise Conflict("invalid_transition", f"Cannot move from {process.status} to {target}",
                       {"from": process.status, "to": target})
    process.status = target
    process.updated_at = clock.now()


def phase(process: Process, now: Optional[datetime] = None) -> str:
    now = now or clock.now()
    if process.status == "PUBLISHED":
        return "submission_open" if now < process.submission_deadline else "awaiting_opening"
    return {
        "DRAFT": "draft", "OPENED": "evaluation", "DECIDED": "decided", "CLOSED": "closed", "CANCELLED": "cancelled",
    }[process.status]


def get(db: Session, process_id: uuid.UUID) -> Process:
    process = db.get(Process, process_id)
    if process is None:
        raise NotFound("process")
    return process


def next_reference(db: Session, prefix: str) -> str:
    year = clock.now().year
    stem = f"{prefix}-{year}-"
    count = db.execute(select(func.count(Process.id)).where(Process.reference_number.like(f"{stem}%"))).scalar_one()
    n = count + 1
    while db.execute(select(Process.id).where(Process.reference_number == f"{stem}{n:04d}")).first():
        n += 1
    return f"{stem}{n:04d}"


def _validate_times(deadline: datetime, opening_time: Optional[datetime]) -> None:
    if deadline.tzinfo is None:
        raise Invalid("timezone_required", "Deadline must include a timezone")
    if opening_time is not None and opening_time < deadline:
        raise Invalid("opening_before_deadline", "Opening time cannot be before the submission deadline")


def create(db: Session, ctx: AuthContext, data: dict) -> Process:
    definition = get_definition(data["process_type"])
    authorization.require(ctx, definition.create_permission)
    details = definition.validate_details(data.get("details") or {})
    _validate_times(data["submission_deadline"], data.get("opening_time"))
    cats = category_service.get_many(db, data.get("category_ids") or [])
    reference = (data.get("reference_number") or "").strip() or next_reference(db, definition.reference_prefix)
    if db.execute(select(Process.id).where(Process.reference_number == reference)).first():
        raise Conflict("reference_taken", "This reference number is already used")
    now = clock.now()
    process = Process(
        id=uuid.uuid4(), organization_id=default_organization(db).id, process_type=definition.key,
        reference_number=reference, title=data["title"].strip(), description=data.get("description", "").strip(),
        status="DRAFT", details=details, submission_deadline=data["submission_deadline"],
        opening_time=data.get("opening_time"), contact_name=data.get("contact_name", ""),
        contact_email=data.get("contact_email", ""), contact_phone=data.get("contact_phone", ""),
        created_by=ctx.user_id, created_at=now, updated_at=now,
    )
    db.add(process)
    db.flush()
    for c in cats:
        db.add(ProcessCategory(process_id=process.id, category_id=c.id))
    db.add(OpeningPolicyRecord(process_id=process.id, rules=list(definition.default_opening_rules),
                               required_approvals=definition.default_required_approvals,
                               designated_official_ids=[], frozen=False))
    db.add(ProcessParticipant(process_id=process.id, user_id=ctx.user_id, participation="OWNER",
                              granted_by=ctx.user_id, reason="creator", granted_at=now))
    db.flush()
    audit.record(db, "PROCESS_CREATED", ctx.actor(), process_id=process.id,
                 metadata={"type": definition.key, "reference": reference,
                           "category_ids": sorted(str(c.id) for c in cats)})
    return process


def update(db: Session, ctx: AuthContext, process: Process, data: dict) -> Process:
    authorization.require_scope(db, ctx, process, "process.manage", authorization.MANAGE_PARTICIPATIONS)
    if process.status != "DRAFT":
        raise Conflict("not_editable", "Only drafts can be edited; published versions are frozen")
    definition = get_definition(process.process_type)
    changed = []
    for key in ("title", "description", "contact_name", "contact_email", "contact_phone"):
        if key in data and data[key] is not None:
            setattr(process, key, data[key].strip())
            changed.append(key)
    if data.get("details") is not None:
        process.details = definition.validate_details(data["details"])
        changed.append("details")
    if data.get("submission_deadline") is not None or "opening_time" in data:
        deadline = data.get("submission_deadline") or process.submission_deadline
        opening = data.get("opening_time", process.opening_time)
        _validate_times(deadline, opening)
        process.submission_deadline, process.opening_time = deadline, opening
        changed.append("schedule")
    if data.get("category_ids") is not None:
        cats = category_service.get_many(db, data["category_ids"])
        for pc in list(process.categories):
            db.delete(pc)
        db.flush()
        for c in cats:
            db.add(ProcessCategory(process_id=process.id, category_id=c.id))
        changed.append("categories")
    process.updated_at = clock.now()
    db.flush()
    db.refresh(process)
    if changed:
        audit.record(db, "PROCESS_UPDATED", ctx.actor(), process_id=process.id, metadata={"fields": changed})
    return process


def add_document(db: Session, ctx: AuthContext, process: Process, *, kind: str, title: str, filename: str,
                 data: bytes) -> ProcessDocument:
    authorization.require_scope(db, ctx, process, "process.manage", authorization.MANAGE_PARTICIPATIONS)
    if process.status != "DRAFT":
        raise Conflict("not_editable", "Documents can be attached only while the process is a draft")
    upload = documents.validate_upload(filename, data)
    stored = documents.store_plain(db, upload, ctx.actor(), prefix="process-docs", process_id=process.id)
    doc = ProcessDocument(process_id=process.id, stored_file_id=stored.id, kind=kind, title=title or upload.filename)
    db.add(doc)
    db.flush()
    return doc


def snapshot_of(db: Session, process: Process) -> dict:
    return {
        "reference_number": process.reference_number,
        "process_type": process.process_type,
        "title": process.title,
        "description": process.description,
        "details": process.details,
        "submission_deadline": process.submission_deadline.isoformat(),
        "opening_time": process.opening_time.isoformat() if process.opening_time else None,
        "category_ids": sorted(str(pc.category_id) for pc in process.categories),
        "documents": sorted(
            ({"title": d.title, "kind": d.kind, "sha256": d.file.sha256} for d in process.documents),
            key=lambda d: d["sha256"],
        ),
        "contact": {"name": process.contact_name, "email": process.contact_email, "phone": process.contact_phone},
    }


def publish(db: Session, ctx: AuthContext, process: Process) -> dict:
    authorization.require_scope(db, ctx, process, "process.manage", authorization.MANAGE_PARTICIPATIONS)
    definition = get_definition(process.process_type)
    if process.status != "DRAFT":
        raise Conflict("invalid_transition", "Only drafts can be published")
    now = clock.now()
    problems = definition.publish_problems(process, len(process.categories))
    if process.submission_deadline <= now:
        problems.append("deadline_in_past")
    if not process.title.strip():
        problems.append("title_required")
    if problems:
        raise Invalid("not_publishable", "The process is not ready to publish", {"problems": problems})

    snapshot = snapshot_of(db, process)
    content_hash = sha256_hex(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode())
    version = ProcessVersion(id=uuid.uuid4(), process_id=process.id, version_no=1, snapshot=snapshot,
                             content_hash=content_hash, frozen_at=now, frozen_by=ctx.user_id)
    db.add(version)
    db.flush()
    process.current_version_id = version.id
    policy = db.execute(select(OpeningPolicyRecord).where(OpeningPolicyRecord.process_id == process.id)).scalar_one()
    policy.frozen = True
    process.published_at = now
    transition(process, "PUBLISHED")
    audit.record(db, "PROCESS_PUBLISHED", ctx.actor(), process_id=process.id,
                 metadata={"version_no": 1, "content_hash": content_hash, "deadline": process.submission_deadline,
                           "opening_policy": {"rules": policy.rules, "required_approvals": policy.required_approvals}})
    vault_row = None
    if definition.sealed:
        vault_row = vault_service.create_vault(db, process)
        audit.record(db, "VAULT_CREATED", ctx.actor(), process_id=process.id,
                     metadata={"vault_id": vault_row.id, "kms_provider": vault_row.kms_provider})
    snap = None
    if definition.distribution == "category_match":
        snap = distribution.create_initial_distribution(db, process, ctx.actor())
    return {
        "version": {"version_no": 1, "content_hash": content_hash},
        "distribution": {"snapshot_id": str(snap.id), "recipient_count": snap.recipient_count,
                         "snapshot_hash": snap.snapshot_hash} if snap else None,
        "vault_id": str(vault_row.id) if vault_row else None,
    }


def cancel(db: Session, ctx: AuthContext, process: Process, reason: str) -> None:
    authorization.require_scope(db, ctx, process, "process.manage", authorization.MANAGE_PARTICIPATIONS)
    if len(reason.strip()) < 5:
        raise Invalid("reason_required", "A cancellation reason is required")
    transition(process, "CANCELLED")
    process.cancelled_reason = reason.strip()
    audit.record(db, "PROCESS_CANCELLED", ctx.actor(), process_id=process.id, metadata={"reason": reason.strip()})


def vault_of(db: Session, process: Process) -> Optional[Vault]:
    return db.execute(select(Vault).where(Vault.process_id == process.id)).scalar_one_or_none()


def submitted(db: Session, process: Process) -> List[Submission]:
    return list(db.execute(
        select(Submission).where(Submission.process_id == process.id, Submission.current_version_id.is_not(None))
        .order_by(Submission.submitted_at)
    ).scalars())


def counts(db: Session, process: Process) -> dict:
    recipients = db.execute(select(func.count(DistributionRecipient.id)).where(
        DistributionRecipient.process_id == process.id)).scalar_one()
    submissions = db.execute(select(func.count(Submission.id)).where(
        Submission.process_id == process.id, Submission.current_version_id.is_not(None))).scalar_one()
    return {"recipients": recipients, "submissions": submissions}


def timeline(db: Session, process: Process) -> List[dict]:
    definition = get_definition(process.process_type)
    now = clock.now()
    vault_row = vault_of(db, process)
    decision = db.execute(select(Decision).where(Decision.process_id == process.id)
                          .order_by(Decision.decided_at.desc()).limit(1)).scalar_one_or_none()
    first_snapshot = db.execute(select(DistributionSnapshot).where(
        DistributionSnapshot.process_id == process.id, DistributionSnapshot.kind == "INITIAL")).scalar_one_or_none()
    published = process.published_at is not None
    deadline_passed = published and now >= process.submission_deadline
    opened = vault_row is not None and vault_row.status == "OPENED"
    stage_state = {
        "draft": ("done", process.created_at),
        "published": ("done" if published else "pending", process.published_at),
        "notified": ("done" if first_snapshot else "pending", first_snapshot.created_at if first_snapshot else None),
        "submission": ("done" if deadline_passed else ("current" if published else "pending"), None),
        "deadline": ("done" if deadline_passed else "pending", process.submission_deadline),
        "opening": ("done" if opened else ("current" if deadline_passed else "pending"),
                    vault_row.opened_at if vault_row else None),
        "evaluation": ("done" if decision else ("current" if opened else "pending"), None),
        "decision": ("done" if decision else "pending", decision.decided_at if decision else None),
        "closed": ("done" if process.status == "CLOSED" else ("current" if decision else "pending"),
                   process.closed_at),
    }
    if process.status == "DRAFT":
        stage_state["draft"] = ("current", process.created_at)
    result = []
    for key in definition.timeline:
        state, at = stage_state.get(key, ("pending", None))
        result.append({"key": key, "state": state, "at": at.isoformat() if at else None})
    if process.status == "CANCELLED":
        result.append({"key": "cancelled", "state": "current", "at": process.updated_at.isoformat()})
    return result
