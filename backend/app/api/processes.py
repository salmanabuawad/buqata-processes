"""Processes, distribution, submissions, opening, evaluation, protocols."""
from __future__ import annotations

import json
import uuid
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_context
from app.api.schemas import (
    ApprovalBody,
    CancelBody,
    DecisionBody,
    DistributionPreviewBody,
    ParticipantBody,
    ProcessCreate,
    ProcessUpdate,
    ProtocolBody,
    PublishBody,
)
from app.core import clock
from app.core.errors import Invalid, NotFound
from app.db import get_db
from app.models import Process, ProcessDocument, ProcessParticipant, User
from app.processes.registry import get_definition
from app.services import (
    audit,
    authorization,
    distribution,
    documents,
    evaluation,
    notifications,
    opening,
    processes as process_service,
    protocols,
    reporting,
    submissions,
)
from app.services.categories import breadcrumb
from app.services.identity import AuthContext

router = APIRouter(tags=["processes"])


def process_view(db: Session, ctx: AuthContext, process: Process) -> dict:
    locale = ctx.user.locale or "he"
    definition = get_definition(process.process_type)
    staff = ctx.has("process.read")
    vault_row = process_service.vault_of(db, process)
    counts = process_service.counts(db, process)
    view = {
        "id": str(process.id), "process_type": process.process_type, "type_names": definition.names,
        "reference_number": process.reference_number, "title": process.title, "description": process.description,
        "status": process.status, "phase": process_service.phase(process), "details": process.details,
        "submission_deadline": process.submission_deadline.isoformat(),
        "opening_time": process.opening_at.isoformat(),
        "published_at": process.published_at.isoformat() if process.published_at else None,
        "contact": {"name": process.contact_name, "email": process.contact_email, "phone": process.contact_phone},
        "categories": [{"id": str(pc.category_id), "path": breadcrumb(db, pc.category, locale)}
                       for pc in process.categories],
        "documents": [{"id": str(d.id), "kind": d.kind, "title": d.title, "filename": d.file.original_filename,
                       "size_bytes": d.file.size_bytes, "sha256": d.file.sha256} for d in process.documents],
        "document_requirements": [
            {"kind": r.kind, "required": r.required, "extensions": list(r.extensions), "multiple": r.multiple,
             "names": r.names} for r in definition.document_requirements
        ],
        "timeline": process_service.timeline(db, process),
        "vault_status": vault_row.status if vault_row else None,
        "server_time": clock.now().isoformat(),
    }
    if staff:
        participation = authorization.participation(db, ctx, process)
        decision = evaluation.latest_decision(db, process)
        creator = db.get(User, process.created_by)
        view.update({
            "created_by": creator.full_name if creator else None,
            "created_at": process.created_at.isoformat(),
            "recipient_count": counts["recipients"],
            "sealed_count": counts["submissions"],
            "my_participation": sorted(participation),
            "participants": reporting.participants(db, process),
            "opening_policy": reporting.opening_policy_summary(db, process),
            "cancelled_reason": process.cancelled_reason,
            "decision": None if decision is None else {
                "decision_type": decision.decision_type, "reason": decision.reason,
                "supplier_name": (decision.metadata_ or {}).get("supplier_name"),
                "selected_submission_id": str(decision.subject_submission_id) if decision.subject_submission_id else None,
                "decided_at": decision.decided_at.isoformat(),
                "decided_by": (db.get(User, decision.decided_by).full_name if decision.decided_by else None),
            },
            "can": {
                "edit": process.status == "DRAFT" and ctx.has("process.manage") and bool(participation & {"OWNER", "TEAM"}),
                "open": process.status == "PUBLISHED" and ctx.has("opening.initiate"),
                "read_content": ctx.has("submission.read_opened") and bool(participation & set(authorization.CONTENT_PARTICIPATIONS)),
                "decide": process.status == "OPENED" and ctx.has("decision.record") and bool(participation & set(authorization.CONTENT_PARTICIPATIONS)),
                "protocol": ctx.has("protocol.generate") and bool(participation & set(authorization.CONTENT_PARTICIPATIONS)),
                "monitor": ctx.has("process.monitor"),
            },
        })
    return view


def _get_visible(db: Session, ctx: AuthContext, process_id: uuid.UUID) -> Process:
    process = process_service.get(db, process_id)
    if not authorization.can_view_process(db, ctx, process):
        raise NotFound("process")
    return process


@router.get("/processes")
def list_processes(process_type: Optional[str] = None, status: Optional[str] = None, q: str = "",
                   limit: int = 50, offset: int = 0, ctx: AuthContext = Depends(current_context),
                   db: Session = Depends(get_db)):
    authorization.require(ctx, "process.read")
    stmt = select(Process)
    if process_type:
        stmt = stmt.where(Process.process_type == process_type)
    if status:
        stmt = stmt.where(Process.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Process.title.ilike(like), Process.reference_number.ilike(like)))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(Process.created_at.desc()).limit(min(max(limit, 1), 200))
                      .offset(max(offset, 0))).scalars().all()
    items = []
    for p in rows:
        c = process_service.counts(db, p)
        items.append({"id": str(p.id), "process_type": p.process_type, "reference_number": p.reference_number,
                      "title": p.title, "status": p.status, "phase": process_service.phase(p),
                      "submission_deadline": p.submission_deadline.isoformat(),
                      "published_at": p.published_at.isoformat() if p.published_at else None,
                      "recipient_count": c["recipients"], "sealed_count": c["submissions"],
                      "categories": [breadcrumb(db, pc.category, ctx.user.locale) for pc in p.categories]})
    return {"total": total, "items": items}


@router.post("/processes")
def create_process(body: ProcessCreate, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    process = process_service.create(db, ctx, body.model_dump())
    db.commit()
    return process_view(db, ctx, process)


@router.get("/processes/{process_id}")
def get_process(process_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    return process_view(db, ctx, _get_visible(db, ctx, process_id))


@router.patch("/processes/{process_id}")
def update_process(process_id: uuid.UUID, body: ProcessUpdate, ctx: AuthContext = Depends(current_context),
                   db: Session = Depends(get_db)):
    process = process_service.get(db, process_id)
    process_service.update(db, ctx, process, body.model_dump(exclude_unset=True))
    db.commit()
    return process_view(db, ctx, process)


@router.post("/processes/{process_id}/documents")
async def add_process_document(process_id: uuid.UUID, kind: str = Form("attachment"), title: str = Form(""),
                               file: UploadFile = File(...), ctx: AuthContext = Depends(current_context),
                               db: Session = Depends(get_db)):
    if kind not in ("specification", "attachment"):
        raise Invalid("invalid_kind", "kind must be specification or attachment")
    process = process_service.get(db, process_id)
    doc = process_service.add_document(db, ctx, process, kind=kind, title=title, filename=file.filename or "file",
                                       data=await file.read())
    db.commit()
    return {"id": str(doc.id)}


@router.get("/processes/{process_id}/documents/{document_id}")
def get_process_document(process_id: uuid.UUID, document_id: uuid.UUID, ctx: AuthContext = Depends(current_context),
                         db: Session = Depends(get_db)):
    process = _get_visible(db, ctx, process_id)
    doc = db.get(ProcessDocument, document_id)
    if doc is None or doc.process_id != process.id:
        raise NotFound("document")
    data = documents.read_plain(db, doc.file, ctx.actor(), process.id)
    return _file_response(data, doc.file.mime_type, doc.file.original_filename)


def _file_response(data: bytes, mime: str, filename: str) -> Response:
    disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(content=data, media_type=mime, headers={"Content-Disposition": disposition,
                                                            "Cache-Control": "no-store"})


@router.post("/distribution/preview")
def preview_distribution(body: DistributionPreviewBody, ctx: AuthContext = Depends(current_context),
                         db: Session = Depends(get_db)):
    authorization.require_any(ctx, ["process.create.rfq", "process.monitor"])
    matched = distribution.preview(db, body.category_ids, body.service_regions)
    return {
        "count": len(matched),
        "suppliers": [{"id": str(m.supplier.id), "company_name": m.supplier.company_name, "city": m.supplier.city,
                       "relations": sorted({x.relation for x in m.matches})} for m in matched],
        "editable": False,
    }


@router.post("/processes/{process_id}/publish")
def publish(process_id: uuid.UUID, body: PublishBody, ctx: AuthContext = Depends(current_context),
            db: Session = Depends(get_db)):
    process = process_service.get(db, process_id)
    result = process_service.publish(db, ctx, process)
    db.commit()
    return {**process_view(db, ctx, process), "publication": result}


@router.post("/processes/{process_id}/cancel")
def cancel(process_id: uuid.UUID, body: CancelBody, ctx: AuthContext = Depends(current_context),
           db: Session = Depends(get_db)):
    process = process_service.get(db, process_id)
    process_service.cancel(db, ctx, process, body.reason)
    db.commit()
    return process_view(db, ctx, process)


@router.get("/processes/{process_id}/distribution")
def fairness(process_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    process = process_service.get(db, process_id)
    return reporting.fairness(db, ctx, process, ctx.user.locale)


@router.post("/processes/{process_id}/participants")
def add_participant(process_id: uuid.UUID, body: ParticipantBody, ctx: AuthContext = Depends(current_context),
                    db: Session = Depends(get_db)):
    process = process_service.get(db, process_id)
    authorization.require_scope(db, ctx, process, "process.manage", ("OWNER",))
    user = db.get(User, body.user_id)
    if user is None or user.kind != "staff":
        raise Invalid("invalid_user", "Participants must be municipal staff")
    db.add(ProcessParticipant(process_id=process.id, user_id=user.id, participation=body.participation,
                              granted_by=ctx.user_id, reason=body.reason, granted_at=clock.now()))
    audit.record(db, "CONTENT_ACCESS_GRANTED" if body.participation == "CONTENT_ACCESS" else "PARTICIPANT_ADDED",
                 ctx.actor(), process_id=process.id,
                 metadata={"user_id": user.id, "participation": body.participation, "reason": body.reason})
    db.commit()
    return {"ok": True}


# ---- invitations & supplier submission ------------------------------------------------

@router.get("/invitations/{token}", tags=["submissions"])
def open_invitation(token: str, db: Session = Depends(get_db)):
    recipient = distribution.recipient_by_token(db, token)
    if recipient is None:
        raise NotFound("invitation")
    if recipient.opened_at is None:
        recipient.opened_at = clock.now()
        audit.record(db, "INVITATION_OPENED", audit.Actor(None, "supplier", None), process_id=recipient.process_id,
                     metadata={"supplier_id": recipient.supplier_id})
        db.commit()
    process = db.get(Process, recipient.process_id)
    return {"process_id": str(process.id), "reference_number": process.reference_number, "title": process.title}


@router.post("/processes/{process_id}/submission/start", tags=["submissions"])
def start_submission(process_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    process = process_service.get(db, process_id)
    submission = submissions.start(db, ctx, process)
    db.commit()
    return submissions.receipt(db, process, submission)


@router.get("/processes/{process_id}/submission", tags=["submissions"])
def my_submission(process_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    authorization.require(ctx, "submission.create")
    process = _get_visible(db, ctx, process_id)
    submission = submissions.own_submission(db, ctx, process)
    return None if submission is None else submissions.receipt(db, process, submission)


@router.post("/processes/{process_id}/submission", tags=["submissions"])
async def submit(process_id: uuid.UUID, payload: str = Form(...), kinds: List[str] = Form(default=[]),
                 files: List[UploadFile] = File(default=[]), ctx: AuthContext = Depends(current_context),
                 db: Session = Depends(get_db)):
    try:
        parsed = json.loads(payload)
    except ValueError as exc:
        raise Invalid("validation_error", "payload must be JSON") from exc
    if not isinstance(parsed, dict):
        raise Invalid("validation_error", "payload must be a JSON object")
    if len(kinds) != len(files):
        raise Invalid("validation_error", "Each file needs a kind")
    if len(files) > 12:
        raise Invalid("too_many_files", "At most 12 files per submission")
    process = process_service.get(db, process_id)
    blobs = [(kind, f.filename or "file", await f.read()) for kind, f in zip(kinds, files)]
    receipt = submissions.submit(db, ctx, process, parsed, blobs)
    db.commit()
    return receipt


# ---- opening -----------------------------------------------------------------------------

@router.get("/processes/{process_id}/opening", tags=["opening"])
def opening_status(process_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    return opening.status(db, ctx, process_service.get(db, process_id))


@router.post("/processes/{process_id}/opening/requests", tags=["opening"])
def request_opening(process_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    result = opening.request_opening(db, ctx, process_service.get(db, process_id))
    alerts = result.pop("_alert_event_ids", [])
    db.commit()
    for event_id in alerts:
        notifications.alert_oversight(event_id)
    return result


@router.post("/opening-requests/{request_id}/approve", tags=["opening"])
def approve_opening(request_id: uuid.UUID, body: ApprovalBody, ctx: AuthContext = Depends(current_context),
                    db: Session = Depends(get_db)):
    result = opening.approve(db, ctx, request_id, "APPROVE", body.reason)
    alerts = result.pop("_alert_event_ids", [])
    db.commit()
    for event_id in alerts:
        notifications.alert_oversight(event_id)
    return result


@router.post("/opening-requests/{request_id}/reject", tags=["opening"])
def reject_opening(request_id: uuid.UUID, body: ApprovalBody, ctx: AuthContext = Depends(current_context),
                   db: Session = Depends(get_db)):
    if len(body.reason.strip()) < 5:
        raise Invalid("reason_required", "A reason is required to reject an opening")
    result = opening.approve(db, ctx, request_id, "REJECT", body.reason)
    db.commit()
    return result


# ---- evaluation --------------------------------------------------------------------------

@router.get("/processes/{process_id}/comparison", tags=["evaluation"])
def comparison(process_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    result = evaluation.comparison(db, ctx, process_service.get(db, process_id))
    db.commit()
    return result


@router.get("/submissions/{submission_id}/documents/{document_id}", tags=["evaluation"])
def download_submission_document(submission_id: uuid.UUID, document_id: uuid.UUID,
                                 ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    stored, data = evaluation.download(db, ctx, submission_id, document_id)
    db.commit()
    return _file_response(data, stored.mime_type, stored.original_filename)


@router.post("/processes/{process_id}/decision", tags=["evaluation"])
def decide(process_id: uuid.UUID, body: DecisionBody, ctx: AuthContext = Depends(current_context),
           db: Session = Depends(get_db)):
    process = process_service.get(db, process_id)
    evaluation.record_decision(db, ctx, process, body.decision_type, body.selected_submission_id, body.reason)
    db.commit()
    return process_view(db, ctx, process)


@router.post("/processes/{process_id}/close", tags=["evaluation"])
def close(process_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    process = process_service.get(db, process_id)
    evaluation.close(db, ctx, process)
    db.commit()
    return process_view(db, ctx, process)


# ---- protocols ---------------------------------------------------------------------------

@router.post("/processes/{process_id}/protocols", tags=["protocols"])
def generate_protocol(process_id: uuid.UUID, body: ProtocolBody, ctx: AuthContext = Depends(current_context),
                      db: Session = Depends(get_db)):
    protocol = protocols.generate(db, ctx, process_service.get(db, process_id), body.locale)
    db.commit()
    return {"id": str(protocol.id), "content_hash": protocol.content_hash}


@router.get("/processes/{process_id}/protocols", tags=["protocols"])
def list_protocols(process_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    rows = protocols.list_for(db, ctx, process_service.get(db, process_id))
    names = {u.id: u.full_name for u in db.execute(select(User).where(
        User.id.in_([p.generated_by for p in rows]))).scalars()}
    return [{"id": str(p.id), "protocol_type": p.protocol_type, "locale": p.locale,
             "content_hash": p.content_hash, "audit_head_hash": p.audit_head_hash,
             "generated_at": p.generated_at.isoformat(), "generated_by": names.get(p.generated_by)} for p in rows]


@router.get("/protocols/{protocol_id}/html", tags=["protocols"], response_class=HTMLResponse)
def protocol_html(protocol_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    protocol = protocols.get_html(db, ctx, protocol_id)
    db.commit()
    return HTMLResponse(protocol.html, headers={
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'",
    })

