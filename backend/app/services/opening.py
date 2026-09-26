"""OpeningService — policy evaluation, approvals, vault opening.

Failures that indicate a security problem (too early, wrong network, wrong
device, rejected approval) are recorded as their own audit events in an
independent transaction and alert oversight, then the request is refused.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import Conflict, Forbidden, NotFound
from app.engines.opening_policy import (
    ApprovalView,
    DevicePosture,
    OpeningContext,
    OpeningPolicy,
    PolicyEvaluation,
)
from app.models import OpeningApproval, OpeningPolicyRecord, OpeningRequest, Process, Submission, User
from app.processes.registry import get_definition
from app.services import audit, authorization, notifications, processes as process_service
from app.services import vault as vault_service
from app.services.identity import AuthContext
from app.services.notification_templates import PROCESS_KIND


class OpeningPolicyFailed(Forbidden):
    def __init__(self, evaluation: PolicyEvaluation):
        super().__init__("opening_policy_failed", "The opening policy is not satisfied", evaluation.as_dict())


def policy_record(db: Session, process: Process) -> OpeningPolicyRecord:
    return db.execute(select(OpeningPolicyRecord).where(OpeningPolicyRecord.process_id == process.id)).scalar_one()


def pending_request(db: Session, process: Process) -> Optional[OpeningRequest]:
    return db.execute(select(OpeningRequest).where(
        OpeningRequest.process_id == process.id, OpeningRequest.status == "PENDING")).scalar_one_or_none()


def _device(ctx: AuthContext) -> DevicePosture:
    # Device posture comes from the identity provider (Intune compliance via
    # Entra ID) in production; local sessions carry none.
    return DevicePosture(managed=False, compliant=False, source="none")


def _context(db: Session, ctx: AuthContext, process: Process, record: OpeningPolicyRecord,
             request: Optional[OpeningRequest], extra_approval: Optional[ApprovalView] = None) -> OpeningContext:
    approvals: List[ApprovalView] = []
    if request is not None:
        approvals = [ApprovalView(a.approver_id, bool(a.auth_context.get("mfa")), a.decision) for a in request.approvals]
    if extra_approval is not None and all(a.approver_id != extra_approval.approver_id for a in approvals):
        approvals.append(extra_approval)
    is_participant = bool(authorization.participation(db, ctx, process) & set(authorization.CONTENT_PARTICIPATIONS))
    return OpeningContext(
        now=clock.now(), opening_time=process.opening_at, actor_id=ctx.user_id,
        actor_permissions=ctx.permissions, actor_is_participant=is_participant, actor_mfa=ctx.mfa,
        actor_active=ctx.user.is_active, client_ip=ctx.ip, device=_device(ctx), approvals=approvals,
        required_approvals=record.required_approvals,
        designated_official_ids=[uuid.UUID(i) for i in (record.designated_official_ids or [])],
    )


def _raise_security_events(policy: OpeningPolicy, evaluation: PolicyEvaluation, ctx: AuthContext,
                           process: Process) -> None:
    for failure in evaluation.failures:
        event = policy.failure_event_for(failure)
        audit.record_independent(
            event or "OPENING_REJECTED", ctx.actor(), process_id=process.id,
            metadata={"rule": failure.rule, "code": failure.code, "detail": failure.detail},
        )


def status(db: Session, ctx: AuthContext, process: Process) -> dict:
    authorization.require(ctx, "process.read")
    record = policy_record(db, process)
    request = pending_request(db, process) or db.execute(
        select(OpeningRequest).where(OpeningRequest.process_id == process.id)
        .order_by(OpeningRequest.requested_at.desc()).limit(1)).scalar_one_or_none()
    vault_row = process_service.vault_of(db, process)
    policy = OpeningPolicy.from_config(record.rules)
    evaluation = policy.evaluate(_context(db, ctx, process, record, request if request and request.status == "PENDING" else None))
    approvers = {}
    if request is not None:
        users = db.execute(select(User).where(User.id.in_([a.approver_id for a in request.approvals]))).scalars()
        approvers = {u.id: u.full_name for u in users}
    return {
        "vault_status": vault_row.status if vault_row else None,
        "opened_at": vault_row.opened_at.isoformat() if vault_row and vault_row.opened_at else None,
        "sealed_count": len(process_service.submitted(db, process)),
        "content_sealed": get_definition(process.process_type).content_sealed(process),
        "opening_mode": (process.details or {}).get("opening_mode"),
        "submission_deadline": process.submission_deadline.isoformat(),
        "opening_time": process.opening_at.isoformat(),
        "phase": process_service.phase(process),
        "rules": record.rules,
        "required_approvals": record.required_approvals,
        "evaluation_for_you": evaluation.as_dict(),
        "request": None if request is None else {
            "id": str(request.id), "status": request.status, "requested_at": request.requested_at.isoformat(),
            "approvals": [
                {"approver": approvers.get(a.approver_id, "—"), "decision": a.decision,
                 "decided_at": a.decided_at.isoformat(), "mfa": bool(a.auth_context.get("mfa"))}
                for a in request.approvals
            ],
        },
    }


def _approval_row(ctx: AuthContext, decision: str, reason: str = "") -> OpeningApproval:
    return OpeningApproval(
        approver_id=ctx.user_id, decision=decision, decided_at=clock.now(),
        auth_context={"amr": ctx.amr, "mfa": ctx.mfa, "session_id": str(ctx.session_id), "role": ctx.primary_role},
        client_ip=ctx.ip, device={"source": _device(ctx).source}, reason=reason,
    )


def request_opening(db: Session, ctx: AuthContext, process: Process) -> dict:
    authorization.require(ctx, "opening.initiate")
    if process.status != "PUBLISHED":
        raise Conflict("invalid_transition", "Only a published process can be opened")
    if not get_definition(process.process_type).content_sealed(process):
        raise Conflict("not_sealed", "Offers in this process are not sealed; there is nothing to open")
    if pending_request(db, process) is not None:
        raise Conflict("opening_already_requested", "An opening request is already pending")
    record = policy_record(db, process)
    policy = OpeningPolicy.from_config(record.rules)
    self_approval = ApprovalView(ctx.user_id, ctx.mfa, "APPROVE")
    evaluation = policy.evaluate(_context(db, ctx, process, record, None, self_approval))
    if evaluation.failures:
        _raise_security_events(policy, evaluation, ctx, process)
        raise OpeningPolicyFailed(evaluation)
    request = OpeningRequest(id=uuid.uuid4(), process_id=process.id, requested_by=ctx.user_id,
                             requested_at=clock.now(), status="PENDING")
    db.add(request)
    request.approvals.append(_approval_row(ctx, "APPROVE"))
    db.flush()
    audit.record(db, "OPENING_REQUESTED", ctx.actor(), process_id=process.id,
                 metadata={"request_id": request.id, "evaluation": evaluation.as_dict()})
    audit.record(db, "OPENING_APPROVED", ctx.actor(), process_id=process.id,
                 metadata={"request_id": request.id, "approver_id": ctx.user_id, "mfa": ctx.mfa})
    return _maybe_execute(db, ctx, process, record, policy, request)


def approve(db: Session, ctx: AuthContext, request_id: uuid.UUID, decision: str, reason: str = "") -> dict:
    authorization.require(ctx, "opening.approve")
    request = db.get(OpeningRequest, request_id)
    if request is None:
        raise NotFound("opening request")
    process = process_service.get(db, request.process_id)
    if request.status != "PENDING":
        raise Conflict("request_not_pending", "This opening request is no longer pending")
    record = policy_record(db, process)
    designated = {uuid.UUID(i) for i in (record.designated_official_ids or [])}
    if designated and ctx.user_id not in designated:
        audit.record_independent("FAILED_MULTI_APPROVAL", ctx.actor(), process_id=process.id,
                                 metadata={"request_id": request.id, "code": "not_designated"})
        raise Forbidden("not_designated", "You are not a designated opening official for this process")
    if any(a.approver_id == ctx.user_id for a in request.approvals):
        audit.record_independent("FAILED_MULTI_APPROVAL", ctx.actor(), process_id=process.id,
                                 metadata={"request_id": request.id, "code": "duplicate_approval"})
        raise Conflict("already_approved", "You have already recorded a decision on this request")
    policy = OpeningPolicy.from_config(record.rules)
    if decision == "REJECT":
        request.approvals.append(_approval_row(ctx, "REJECT", reason))
        request.status = "REJECTED"
        audit.record(db, "OPENING_REJECTED", ctx.actor(), process_id=process.id,
                     metadata={"request_id": request.id, "reason": reason})
        return {"status": "REJECTED"}
    evaluation = policy.evaluate(_context(db, ctx, process, record, request,
                                          ApprovalView(ctx.user_id, ctx.mfa, "APPROVE")))
    hard_failures = [f for f in evaluation.failures if f.rule != "multi_approval"]
    if hard_failures:
        _raise_security_events(policy, PolicyEvaluation(hard_failures), ctx, process)
        raise OpeningPolicyFailed(evaluation)
    request.approvals.append(_approval_row(ctx, "APPROVE"))
    db.flush()
    audit.record(db, "OPENING_APPROVED", ctx.actor(), process_id=process.id,
                 metadata={"request_id": request.id, "approver_id": ctx.user_id, "mfa": ctx.mfa})
    return _maybe_execute(db, ctx, process, record, policy, request)


def _maybe_execute(db: Session, ctx: AuthContext, process: Process, record: OpeningPolicyRecord,
                   policy: OpeningPolicy, request: OpeningRequest) -> dict:
    db.refresh(request)
    evaluation = policy.evaluate(_context(db, ctx, process, record, request))
    request.last_evaluation = evaluation.as_dict()
    if not evaluation.satisfied:
        return {"status": "PENDING", "request_id": str(request.id), "evaluation": evaluation.as_dict()}
    return _execute(db, ctx, process, request, evaluation)


def _execute(db: Session, ctx: AuthContext, process: Process, request: OpeningRequest,
             evaluation: PolicyEvaluation) -> dict:
    vault_row = process_service.vault_of(db, process)
    submissions = process_service.submitted(db, process)
    report = vault_service.open_vault(db, vault_row, submissions, ctx.actor(), request.id)
    request.status = "EXECUTED"
    request.executed_at = vault_row.opened_at
    process_service.transition(process, "OPENED")
    audit.record(db, "VAULT_OPENED", ctx.actor(), process_id=process.id,
                 metadata={"request_id": request.id, "opened_at": vault_row.opened_at,
                           "submissions": report.opened_submissions, "verified_files": report.verified_files,
                           "integrity_failures": len(report.failed_files),
                           "approvers": [str(a.approver_id) for a in request.approvals if a.decision == "APPROVE"]})
    _notify_submitters(db, process, submissions, vault_row.opened_at)
    return {
        "status": "EXECUTED", "request_id": str(request.id), "opened_at": vault_row.opened_at.isoformat(),
        "opened_submissions": report.opened_submissions, "verified_files": report.verified_files,
        "integrity_failures": report.failed_files, "evaluation": evaluation.as_dict(),
        "_alert_event_ids": report.alert_event_ids,
    }


def _notify_submitters(db: Session, process: Process, submissions: List[Submission], opened_at) -> None:
    from app.services.distribution import _supplier_user

    local = notifications.local_time(opened_at)
    recipients = []
    for submission in submissions:
        supplier = submission.supplier
        if supplier is None:
            continue
        user = _supplier_user(db, supplier)
        recipients.append(notifications.Recipient(user.id if user else None, supplier.email,
                                                  supplier.preferred_locale or "he", supplier.id))
    kind = PROCESS_KIND.get(process.process_type, {})
    notifications.enqueue(
        db, "VAULT_OPENED", recipients,
        {"reference": process.reference_number, "opened_date": local.strftime("%d.%m.%Y"),
         "opened_time": local.strftime("%H:%M"), "count": len(submissions)},
        process_id=process.id, link=f"/supplier/opportunity/?id={process.id}",
        per_recipient_params=lambda r: {"kind": kind.get(r.locale, kind.get("he", ""))},
    )
