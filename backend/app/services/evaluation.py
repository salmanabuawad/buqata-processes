"""Comparison of opened submissions and recording of decisions.

The comparison never ranks, scores or highlights a winner. Decisions are
recorded only by an authorized participant, with a reason.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import Conflict, Forbidden, Invalid, NotFound
from app.models import Decision, Process, Submission, SubmissionDocument, SupplierDocument
from app.processes.registry import get_definition
from app.services import audit, authorization, notifications, processes as process_service
from app.services import vault as vault_service
from app.services.distribution import _supplier_user
from app.services.identity import AuthContext


def comparison(db: Session, ctx: AuthContext, process: Process) -> dict:
    authorization.require_scope(db, ctx, process, "submission.read_opened")
    definition = get_definition(process.process_type)
    vault_row = process_service.vault_of(db, process)
    submissions = process_service.submitted(db, process)
    payloads = vault_service.read_payloads(vault_row, submissions, ctx.actor())
    today = clock.now().date()
    rows = []
    for submission in submissions:
        version = submission.current_version
        kinds = [d.kind for d in version.documents]
        missing = definition.missing_documents(kinds)
        certificates = db.execute(select(SupplierDocument).where(
            SupplierDocument.supplier_id == submission.supplier_id)).scalars().all()
        payload = payloads.get(submission.id)
        rows.append({
            "submission_id": str(submission.id),
            "receipt_number": submission.receipt_number,
            "supplier": {"id": str(submission.supplier.id), "name": submission.supplier.company_name,
                         "company_number": submission.supplier.company_number},
            "submitted_at": submission.submitted_at.isoformat(),
            "version_no": version.version_no,
            "values": definition.comparison_row(payload) if payload is not None else None,
            "integrity_ok": payload is not None and all(d.file.integrity_status == "OK" for d in version.documents),
            "documents": [
                {"id": str(d.id), "kind": d.kind, "filename": d.file.original_filename,
                 "size_bytes": d.file.size_bytes, "sha256": d.file.sha256, "integrity": d.file.integrity_status}
                for d in version.documents
            ],
            "required_documents": {"complete": not missing, "missing": missing},
            "certificates": {
                "count": len(certificates),
                "expired": sum(1 for c in certificates if c.expires_on and c.expires_on < today),
            },
        })
        audit.record(db, "PROPOSAL_VIEWED", ctx.actor(), process_id=process.id, submission_id=submission.id,
                     metadata={"view": "comparison"})
    return {"process_id": str(process.id), "opened_at": vault_row.opened_at.isoformat(), "rows": rows,
            "ranking": None}


def download(db: Session, ctx: AuthContext, submission_id: uuid.UUID, document_id: uuid.UUID):
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise NotFound("submission")
    process = process_service.get(db, submission.process_id)
    authorization.require_scope(db, ctx, process, "submission.read_opened")
    document = db.get(SubmissionDocument, document_id)
    if document is None or document.version.submission_id != submission.id:
        raise NotFound("document")
    data = vault_service.read_document(db, process_service.vault_of(db, process), submission, document, ctx.actor())
    audit.record(db, "PROPOSAL_DOWNLOADED", ctx.actor(), process_id=process.id, submission_id=submission.id,
                 metadata={"document_id": document.id, "sha256": document.file.sha256, "verified": True})
    return document.file, data


def record_decision(db: Session, ctx: AuthContext, process: Process, decision_type: str,
                    selected_submission_id: Optional[uuid.UUID], reason: str) -> Decision:
    authorization.require_scope(db, ctx, process, "decision.record")
    if process.status != "OPENED":
        raise Conflict("invalid_transition", "A decision can be recorded only after opening")
    if len(reason.strip()) < 10:
        raise Invalid("reason_required", "Explain the decision (at least 10 characters)")
    if decision_type not in ("AWARD", "NO_AWARD"):
        raise Invalid("invalid_decision_type", "Decision must be AWARD or NO_AWARD")
    selected = None
    if decision_type == "AWARD":
        if selected_submission_id is None:
            raise Invalid("submission_required", "Choose the selected submission")
        selected = db.get(Submission, selected_submission_id)
        if selected is None or selected.process_id != process.id or selected.status != "OPENED":
            raise Invalid("invalid_submission", "The selected submission is not an opened submission of this process")
        if selected.current_version and any(d.file.integrity_status == "FAILED" for d in selected.current_version.documents):
            raise Forbidden("file_integrity_failure", "A submission with failed integrity cannot be selected")
    elif selected_submission_id is not None:
        raise Invalid("unexpected_submission", "A no-award decision does not select a submission")
    decision = Decision(process_id=process.id, subject_submission_id=selected.id if selected else None,
                        decision_type=decision_type, reason=reason.strip(), decided_by=ctx.user_id,
                        decided_at=clock.now(),
                        metadata_={"supplier_name": selected.supplier.company_name if selected else None})
    db.add(decision)
    process_service.transition(process, "DECIDED")
    db.flush()
    audit.record(db, "DECISION_RECORDED", ctx.actor(), process_id=process.id,
                 submission_id=selected.id if selected else None,
                 metadata={"decision_id": decision.id, "decision_type": decision_type})
    recipients = []
    for submission in process_service.submitted(db, process):
        user = _supplier_user(db, submission.supplier)
        recipients.append(notifications.Recipient(user.id if user else None, submission.supplier.email,
                                                  submission.supplier.preferred_locale or "he", submission.supplier_id))
    notifications.enqueue(
        db, "DECISION_RECORDED", recipients,
        {"reference": process.reference_number, "title": process.title,
         "contact": process.contact_email or process.contact_name or "—"},
        process_id=process.id, link=f"/supplier/opportunity/?id={process.id}",
    )
    return decision


def latest_decision(db: Session, process: Process) -> Optional[Decision]:
    return db.execute(select(Decision).where(Decision.process_id == process.id)
                      .order_by(Decision.decided_at.desc()).limit(1)).scalar_one_or_none()


def close(db: Session, ctx: AuthContext, process: Process) -> None:
    from app.models import Protocol

    authorization.require_scope(db, ctx, process, "process.manage", authorization.MANAGE_PARTICIPATIONS)
    has_protocol = db.execute(select(Protocol.id).where(Protocol.process_id == process.id)).first()
    if not has_protocol:
        raise Conflict("protocol_required", "Generate the protocol before closing")
    process_service.transition(process, "CLOSED")
    process.closed_at = clock.now()
    audit.record(db, "PROCESS_CLOSED", ctx.actor(), process_id=process.id)
