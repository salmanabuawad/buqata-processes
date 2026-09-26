"""Supplier submissions: start, seal, receipt."""
from __future__ import annotations

import secrets
import uuid
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import Conflict, Forbidden, Invalid
from app.models import DistributionRecipient, Process, Submission, SubmissionVersion
from app.processes.registry import get_definition
from app.services import audit, authorization, documents, notifications, processes as process_service
from app.services import vault as vault_service
from app.services.identity import AuthContext
from app.services.vault import IncomingFile


def _recipient_or_403(db: Session, ctx: AuthContext, process: Process) -> DistributionRecipient:
    authorization.require(ctx, "submission.create")
    recipient = authorization.supplier_recipient(db, ctx, process)
    if recipient is None:
        raise Forbidden("not_invited", "Your company is not in this process's distribution")
    return recipient


def _require_open(process: Process) -> None:
    if process.status != "PUBLISHED":
        raise Conflict("not_accepting_submissions", "This process is not accepting submissions")
    if clock.now() >= process.submission_deadline:
        raise Conflict("deadline_passed", "The submission deadline has passed")


def _receipt_number(process: Process) -> str:
    return f"{process.reference_number}-S{secrets.token_hex(4).upper()}"


def own_submission(db: Session, ctx: AuthContext, process: Process) -> Optional[Submission]:
    if ctx.supplier_id is None:
        return None
    return db.execute(select(Submission).where(
        Submission.process_id == process.id, Submission.supplier_id == ctx.supplier_id)).scalar_one_or_none()


def start(db: Session, ctx: AuthContext, process: Process) -> Submission:
    recipient = _recipient_or_403(db, ctx, process)
    _require_open(process)
    submission = own_submission(db, ctx, process)
    if submission is None:
        submission = Submission(id=uuid.uuid4(), process_id=process.id, supplier_id=ctx.supplier_id,
                                receipt_number=_receipt_number(process), status="STARTED", started_at=clock.now())
        db.add(submission)
        db.flush()
        audit.record(db, "SUBMISSION_STARTED", ctx.actor(), process_id=process.id, submission_id=submission.id)
    if recipient.submission_started_at is None:
        recipient.submission_started_at = clock.now()
    return submission


def submit(db: Session, ctx: AuthContext, process: Process, payload: dict,
           files: Sequence[Tuple[str, str, bytes]]) -> dict:
    """files: (kind, filename, data)."""
    _recipient_or_403(db, ctx, process)
    _require_open(process)
    definition = get_definition(process.process_type)
    normalised = definition.normalise_submission(payload)

    incoming: List[IncomingFile] = []
    for kind, filename, data in files:
        requirement = definition.requirement(kind)
        if requirement is None:
            raise Invalid("unknown_document_kind", f"Unknown document kind {kind!r}", {"kind": kind})
        upload = documents.validate_upload(filename, data, requirement.extensions)
        incoming.append(IncomingFile(kind, upload.filename, upload.mime_type, upload.data))
    for requirement in definition.document_requirements:
        count = sum(1 for f in incoming if f.kind == requirement.kind)
        if count > 1 and not requirement.multiple:
            raise Invalid("too_many_files", f"Only one {requirement.kind} file is allowed", {"kind": requirement.kind})
    missing = definition.missing_documents([f.kind for f in incoming])
    if missing:
        raise Invalid("missing_documents", "Required documents are missing", {"missing": missing})

    submission = start(db, ctx, process)
    vault_row = process_service.vault_of(db, process)
    previous = submission.current_version
    version_no = (previous.version_no + 1) if previous else 1
    sealed = vault_service.seal_submission(db, vault_row, submission, normalised, incoming, ctx.user_id, version_no)
    if previous is not None:
        previous.is_current = False
        previous.superseded_at = clock.now()
    submission.current_version_id = sealed.version.id
    submission.status = "SUBMITTED"
    submission.submitted_at = sealed.version.submitted_at
    db.flush()

    actor = ctx.actor()
    audit.record(db, "SUBMISSION_UPDATED" if previous else "SUBMISSION_CREATED", actor,
                 process_id=process.id, submission_id=submission.id,
                 metadata={"version_no": version_no, "payload_hash": sealed.payload_hash})
    for kind, filename, size, digest in sealed.files:
        audit.record(db, "FILE_UPLOADED", actor, process_id=process.id, submission_id=submission.id,
                     metadata={"kind": kind, "size": size, "sha256": digest,
                               "sealed": definition.content_sealed(process)})
    audit.record(db, "SUBMISSION_SEALED", actor, process_id=process.id, submission_id=submission.id,
                 metadata={"version_no": version_no, "receipt_hash": sealed.receipt_hash,
                           "file_count": len(sealed.files)})
    template = "SUBMISSION_RECEIPT" if definition.content_sealed(process) else "SUBMISSION_RECEIPT_OPEN"
    notifications.enqueue(
        db, template, [notifications.recipient_for_user(ctx.user)],
        {"reference": process.reference_number, "receipt": submission.receipt_number,
         "submitted_at": notifications.format_datetime(submission.submitted_at),
         "receipt_hash": sealed.receipt_hash},
        process_id=process.id, link=f"/supplier/opportunity/?id={process.id}",
    )
    return receipt(db, process, submission)


def receipt(db: Session, process: Process, submission: Submission) -> dict:
    versions = db.execute(select(SubmissionVersion).where(SubmissionVersion.submission_id == submission.id)
                          .order_by(SubmissionVersion.version_no)).scalars().all()
    current = next((v for v in versions if v.is_current), None)
    return {
        "process_id": str(process.id),
        "reference_number": process.reference_number,
        "submission_id": str(submission.id),
        "receipt_number": submission.receipt_number,
        "status": submission.status,
        "started_at": submission.started_at.isoformat(),
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        "current_version": None if current is None else {
            "version_no": current.version_no,
            "submitted_at": current.submitted_at.isoformat(),
            "payload_hash": current.payload_hash,
            "receipt_hash": current.receipt_hash,
            "files": [
                {"kind": d.kind, "filename": d.file.original_filename, "size_bytes": d.file.size_bytes,
                 "sha256": d.file.sha256}
                for d in current.documents
            ],
        },
        "superseded_versions": [
            {"version_no": v.version_no, "submitted_at": v.submitted_at.isoformat(), "receipt_hash": v.receipt_hash}
            for v in versions if not v.is_current
        ],
    }
