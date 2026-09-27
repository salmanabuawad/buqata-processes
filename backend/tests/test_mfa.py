"""Local TOTP two-step verification: enrolment, sign-in, step-up, replay and opening policy."""
from __future__ import annotations

import base64
import uuid
from datetime import timedelta

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from app.api import auth as auth_api
from app.core import clock, totp
from app.models import AuditEvent, OpeningPolicyRecord, User
from app.services import mfa
from app.services.audit import Actor, verify_audit_chain
from tests.conftest import PASSWORD, ApiClient, create_rfq, submit_offer


@pytest.fixture(autouse=True)
def _fresh_limiter():
    auth_api._attempts.clear()
    yield
    auth_api._attempts.clear()


def _events(db, event_type):
    return db.execute(select(AuditEvent).where(AuditEvent.event_type == event_type)).scalars().all()


def _secret_from(enrolment) -> bytes:
    raw = enrolment["secret"]
    return base64.b32decode(raw + "=" * (-len(raw) % 8))


def _code(secret: bytes, offset_steps: int = 0) -> str:
    return totp.code_at(secret, totp.time_step(clock.now().timestamp()) + offset_steps)


def _enrol(client: ApiClient) -> bytes:
    enrolment = client.post("/api/v1/auth/mfa/enroll").json()
    secret = _secret_from(enrolment)
    response = client.post("/api/v1/auth/mfa/confirm", json={"code": _code(secret)})
    assert response.status_code == 200, response.text
    return secret


def _next_step():
    clock.set_now(clock.now() + timedelta(seconds=totp.STEP_SECONDS))


def test_rfc6238_reference_vectors():
    # RFC 6238 appendix B, SHA-1, truncated to 6 digits.
    secret = b"12345678901234567890"
    for unix, expected in [(59, "287082"), (1111111109, "081804"), (1234567890, "005924"), (2000000000, "279037")]:
        assert totp.code_at(secret, totp.time_step(unix)) == expected


def test_matching_step_allows_drift_and_refuses_replay_and_garbage():
    secret = totp.new_secret()
    now = 1_800_000_000
    step = totp.time_step(now)
    assert totp.matching_step(secret, totp.code_at(secret, step - 1), now) == step - 1
    assert totp.matching_step(secret, totp.code_at(secret, step - 3), now) is None
    assert totp.matching_step(secret, totp.code_at(secret, step), now, after_step=step) is None
    assert totp.matching_step(secret, "abcdef", now) is None
    assert totp.matching_step(secret, "12345", now) is None


def test_enrolment_stores_only_a_kms_wrapped_secret(world, db):
    client = ApiClient("proc@example.com")
    assert client.get("/api/v1/auth/me").json()["mfa_enrolled"] is False
    enrolment = client.post("/api/v1/auth/mfa/enroll").json()
    assert enrolment["otpauth_uri"].startswith("otpauth://totp/")
    secret = _secret_from(enrolment)
    user = db.get(User, world["staff"]["procurement"].id)
    db.refresh(user)
    assert user.totp_secret and secret not in base64.b64decode(user.totp_secret)
    assert enrolment["secret"] not in user.totp_secret
    assert user.totp_enabled_at is None                       # pending until a code is confirmed

    wrong = client.post("/api/v1/auth/mfa/confirm", json={"code": "000000" if _code(secret) != "000000" else "111111"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "invalid_otp"
    assert _events(db, "MFA_FAILED")

    me = client.post("/api/v1/auth/mfa/confirm", json={"code": _code(secret)}).json()
    assert me["mfa_enrolled"] is True and me["mfa"] is True   # confirming also steps up this session
    assert _events(db, "MFA_ENABLED")
    again = client.post("/api/v1/auth/mfa/enroll")
    assert again.status_code == 409 and again.json()["error"]["code"] == "mfa_already_enrolled"


def test_secret_in_the_database_is_useless_without_the_kms(world, db):
    client = ApiClient("proc@example.com")
    _enrol(client)
    user = db.get(User, world["staff"]["procurement"].id)
    db.refresh(user)
    other = world["staff"]["auditor"]
    # A secret copied to another account does not unwrap: the KMS context binds it to its owner.
    other.totp_secret, other.totp_enabled_at = user.totp_secret, clock.now()
    db.commit()
    with pytest.raises(InvalidTag):
        mfa.check_code(other, "123456")
    db.rollback()


def test_sign_in_requires_the_code_once_enrolled(world, db):
    secret = _enrol(ApiClient("proc@example.com"))
    _next_step()
    client = ApiClient()
    body = {"email": "proc@example.com", "password": PASSWORD}
    missing = client.post("/api/v1/auth/login", json=body)
    assert missing.status_code == 401 and missing.json()["error"]["code"] == "mfa_required"
    wrong = client.post("/api/v1/auth/login", json={**body, "otp": "999999" if _code(secret) != "999999" else "888888"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "invalid_otp"
    assert any(e.metadata_.get("reason") == "invalid_otp" for e in _events(db, "LOGIN_FAILED"))

    ok = client.post("/api/v1/auth/login", json={**body, "otp": _code(secret)})
    assert ok.status_code == 200
    client.csrf = ok.json()["csrf_token"]
    assert client.get("/api/v1/auth/me").json()["mfa"] is True
    assert _events(db, "USER_LOGGED_IN")[-1].metadata_["method"] == "password+otp"
    # The same code cannot be used again, even within its 30 seconds.
    replay = ApiClient().post("/api/v1/auth/login", json={**body, "otp": _code(secret)})
    assert replay.status_code == 401 and replay.json()["error"]["code"] == "invalid_otp"


def test_step_up_marks_only_the_session_that_verified(world, db):
    earlier = ApiClient("proc@example.com")        # signed in before enrolment: password only
    enrolling = ApiClient("proc@example.com")
    secret = _enrol(enrolling)
    assert enrolling.get("/api/v1/auth/me").json()["mfa"] is True
    assert earlier.get("/api/v1/auth/me").json()["mfa"] is False

    _next_step()
    response = earlier.post("/api/v1/auth/mfa/verify", json={"code": _code(secret)})
    assert response.status_code == 200 and response.json()["mfa"] is True
    assert _events(db, "MFA_STEP_UP")
    other = ApiClient("auditor@example.com")
    refused = other.post("/api/v1/auth/mfa/verify", json={"code": "123456"})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "mfa_not_enrolled"


def test_repeated_wrong_codes_are_rate_limited(world, db):
    client = ApiClient("proc@example.com")
    secret = _enrol(client)
    bad = "000000" if all(_code(secret, k) != "000000" for k in (-1, 0, 1)) else "111111"
    for _ in range(auth_api._MAX):
        assert client.post("/api/v1/auth/mfa/verify", json={"code": bad}).status_code == 401
    limited = client.post("/api/v1/auth/mfa/verify", json={"code": _code(secret, 1)})
    assert limited.status_code == 429


def test_disable_needs_a_valid_code_and_operator_reset_is_audited(world, db):
    client = ApiClient("proc@example.com")
    secret = _enrol(client)
    _next_step()
    bad = "000000" if all(_code(secret, k) != "000000" for k in (-1, 0, 1)) else "111111"
    assert client.post("/api/v1/auth/mfa/disable", json={"code": bad}).status_code == 401
    me = client.post("/api/v1/auth/mfa/disable", json={"code": _code(secret)}).json()
    assert me["mfa_enrolled"] is False
    user = db.get(User, world["staff"]["procurement"].id)
    db.refresh(user)
    assert user.totp_secret is None

    _enrol(client)
    db.refresh(user)
    mfa.reset(db, user, Actor(None, "cli", None), "lost phone")
    db.commit()
    assert user.totp_secret is None and user.totp_enabled_at is None
    reasons = [e.metadata_.get("by") for e in _events(db, "MFA_DISABLED")]
    assert reasons == ["owner", "operator"]
    assert all(e.severity == "WARNING" for e in _events(db, "MFA_DISABLED"))
    assert verify_audit_chain(db).valid


def test_opening_policy_requiring_mfa_is_satisfied_by_step_up(world, db):
    proc = ApiClient("proc@example.com")
    process = create_rfq(proc, db)
    assert submit_offer(ApiClient("desktop@example.com"), process["id"]).status_code == 200
    policy = db.execute(select(OpeningPolicyRecord).where(
        OpeningPolicyRecord.process_id == uuid.UUID(process["id"]))).scalar_one()
    policy.rules = [r if r["type"] != "identity" else {"type": "identity", "params": {"require_mfa": True}}
                    for r in policy.rules]
    db.commit()
    clock.set_now(clock.now() + timedelta(days=4))
    proc = ApiClient("proc@example.com")
    refused = proc.post(f"/api/v1/processes/{process['id']}/opening/requests")
    assert refused.status_code == 403
    results = refused.json()["error"]["details"]["results"]
    assert any(r["rule"] == "identity" and r["code"] == "mfa_required" for r in results)

    _enrol(proc)                                       # confirming enrolment steps this session up
    opened = proc.post(f"/api/v1/processes/{process['id']}/opening/requests")
    assert opened.status_code == 200 and opened.json()["status"] == "EXECUTED"
