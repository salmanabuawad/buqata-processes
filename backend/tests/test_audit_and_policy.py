"""Audit chain integrity and the opening-policy engine (used by tenders in phase 7)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import db as db_module
from app import db_guards
from app.engines.opening_policy import (
    ApprovalView,
    DevicePosture,
    OpeningContext,
    OpeningPolicy,
)
from app.services import audit
from app.services.audit import Actor

NOW = datetime(2026, 9, 26, 12, 4, tzinfo=timezone.utc)


def _append(db, n):
    for i in range(n):
        audit.record(db, "TEST_EVENT", Actor(None, "test", None), metadata={"i": i})
    db.commit()


def test_chain_verifies(db):
    _append(db, 5)
    report = audit.verify_audit_chain(db)
    assert report.valid and report.checked >= 5


def test_trigger_blocks_update_and_delete(db):
    _append(db, 2)
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE audit_events SET event_type='X' WHERE sequence=1"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM audit_events WHERE sequence=1"))
    db.rollback()


@pytest.mark.parametrize("tamper", [
    "UPDATE audit_events SET metadata='{\"i\": 99}' WHERE sequence = :s",
    "UPDATE audit_events SET occurred_at = '2020-01-01 00:00:00.000000' WHERE sequence = :s",
    "DELETE FROM audit_events WHERE sequence = :s",
])
def test_modification_breaks_chain_verification(db, tamper):
    _append(db, 6)
    target = audit.verify_audit_chain(db).checked - 3
    db.commit()  # end the read transaction so the privileged DDL below is not blocked by it
    # A privileged operator removes the guard first — exactly what the chain must expose.
    with db_module.engine.begin() as conn:
        db_guards.uninstall(conn)
        conn.execute(text(tamper), {"s": target})
        db_guards.install(conn)
    report = audit.verify_audit_chain(db)
    assert not report.valid
    assert report.first_broken_sequence in (target, target + 1)


def _ctx(**overrides):
    base = dict(
        now=NOW, opening_time=NOW - timedelta(minutes=4), actor_id=uuid.uuid4(),
        actor_permissions=frozenset({"opening.initiate", "opening.approve"}), actor_is_participant=True,
        actor_mfa=True, actor_active=True, client_ip="10.20.0.5",
        device=DevicePosture(managed=True, compliant=True, source="intune"),
        approvals=(), required_approvals=3, designated_official_ids=(),
    )
    base.update(overrides)
    return OpeningContext(**base)


TENDER_POLICY = [
    {"type": "time"},
    {"type": "network", "params": {"cidrs": ["10.20.0.0/16"], "label": "municipal"}},
    {"type": "device", "params": {"require_compliant": True}},
    {"type": "identity", "params": {"require_mfa": True}},
    {"type": "role", "params": {"permission": "opening.approve"}},
    {"type": "multi_approval", "params": {"require_mfa_per_approval": True}},
]


def test_three_of_five_stays_locked_at_two_approvals():
    officials = [uuid.uuid4() for _ in range(5)]
    policy = OpeningPolicy.from_config(TENDER_POLICY)
    two = [ApprovalView(officials[0], True, "APPROVE"), ApprovalView(officials[1], True, "APPROVE")]
    evaluation = policy.evaluate(_ctx(approvals=two, designated_official_ids=officials))
    assert not evaluation.satisfied
    multi = next(r for r in evaluation.results if r.rule == "multi_approval")
    assert multi.status == "PENDING" and multi.detail["approved"] == 2
    three = two + [ApprovalView(officials[2], True, "APPROVE")]
    assert policy.evaluate(_ctx(approvals=three, designated_official_ids=officials)).satisfied


def test_undesignated_or_non_mfa_approvals_do_not_count():
    officials = [uuid.uuid4() for _ in range(5)]
    policy = OpeningPolicy.from_config(TENDER_POLICY)
    approvals = [ApprovalView(officials[0], True, "APPROVE"), ApprovalView(officials[1], False, "APPROVE"),
                 ApprovalView(uuid.uuid4(), True, "APPROVE")]
    evaluation = policy.evaluate(_ctx(approvals=approvals, designated_official_ids=officials))
    assert next(r for r in evaluation.results if r.rule == "multi_approval").detail["approved"] == 1


def test_network_policy_blocks_outside_municipal_network():
    policy = OpeningPolicy.from_config(TENDER_POLICY)
    evaluation = policy.evaluate(_ctx(client_ip="203.0.113.9"))
    failure = next(r for r in evaluation.failures if r.rule == "network")
    assert failure.code == "outside_allowed_network"
    assert policy.failure_event_for(failure) == "UNAUTHORIZED_NETWORK_ATTEMPT"


def test_device_and_time_and_mfa_failures_are_typed():
    policy = OpeningPolicy.from_config(TENDER_POLICY)
    evaluation = policy.evaluate(_ctx(now=NOW - timedelta(hours=1), actor_mfa=False,
                                      device=DevicePosture(False, False, source="none")))
    codes = {r.rule: r.code for r in evaluation.failures}
    assert codes == {"time": "before_opening_time", "device": "unmanaged_device", "identity": "mfa_required"}
    events = {policy.failure_event_for(r) for r in evaluation.failures}
    assert {"EARLY_OPEN_ATTEMPT", "UNAUTHORIZED_DEVICE_ATTEMPT"} <= events


def test_rejection_fails_multi_approval():
    policy = OpeningPolicy.from_config([{"type": "multi_approval"}])
    evaluation = policy.evaluate(_ctx(approvals=[ApprovalView(uuid.uuid4(), True, "REJECT")]))
    assert evaluation.failures[0].code == "approval_rejected"
