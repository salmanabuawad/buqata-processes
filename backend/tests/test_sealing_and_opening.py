"""Sealing, opening, integrity, decisions, protocol."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.adapters.storage import get_storage
from app.core import clock
from app.models import AuditEvent, Notification, StoredFile, Submission, SubmissionVersion
from app.services import notifications
from tests.conftest import ApiClient, create_rfq, make_staff, submit_offer


def _events(db, event_type, process_id=None):
    stmt = select(AuditEvent).where(AuditEvent.event_type == event_type)
    if process_id:
        stmt = stmt.where(AuditEvent.process_id == uuid.UUID(str(process_id)))
    return db.execute(stmt).scalars().all()


def _setup_with_offers(db, n=2):
    proc = ApiClient("proc@example.com")
    process = create_rfq(proc, db)
    emails = ["rootit@example.com", "desktop@example.com", "computers@example.com", "desktopar@example.com"][:n]
    for i, email in enumerate(emails):
        response = submit_offer(ApiClient(email), process["id"], price_shekels=80000 + i * 1000)
        assert response.status_code == 200, response.text
    return proc, process


def test_submission_is_stored_encrypted_and_receipt_has_hashes(world, db):
    proc, process = _setup_with_offers(db, 1)
    supplier = ApiClient("rootit@example.com")
    receipt = supplier.get(f"/api/v1/processes/{process['id']}/submission").json()
    assert receipt["status"] == "SUBMITTED"
    assert len(receipt["current_version"]["files"][0]["sha256"]) == 64
    version = db.execute(select(SubmissionVersion)).scalar_one()
    assert b"8000000" not in version.payload_ciphertext          # the price is not in the clear
    stored = db.execute(select(StoredFile).where(StoredFile.encrypted.is_(True))).scalar_one()
    assert not get_storage().get(stored.storage_key).startswith(b"%PDF")


def test_proposal_cannot_be_viewed_before_opening(world, db):
    proc, process = _setup_with_offers(db)
    response = proc.get(f"/api/v1/processes/{process['id']}/comparison")
    assert response.status_code == 403 and response.json()["error"]["code"] == "vault_sealed"
    assert _events(db, "SEALED_ACCESS_DENIED", process["id"])
    detail = proc.get(f"/api/v1/processes/{process['id']}").json()
    assert detail["sealed_count"] == 2 and "rows" not in detail
    fairness = proc.get(f"/api/v1/processes/{process['id']}/distribution").json()
    assert all(r["submitted"] is None for r in fairness["recipients"])  # who submitted stays hidden


def test_system_admin_cannot_bypass_sealed_state(world, db):
    proc, process = _setup_with_offers(db)
    admin = ApiClient("admin@example.com")
    assert admin.get(f"/api/v1/processes/{process['id']}/comparison").status_code == 403
    assert admin.post(f"/api/v1/processes/{process['id']}/opening/requests").status_code == 403
    # Nor after the deadline, nor after self-granting a business role.
    clock.set_now(clock.now() + timedelta(days=4))
    admin = ApiClient("admin@example.com")
    assert admin.post(f"/api/v1/processes/{process['id']}/opening/requests").status_code == 403
    response = admin.post(f"/api/v1/admin/users/{world['staff']['admin'].id}/roles",
                          json={"role_key": "procurement_manager", "reason": "I want to open it"})
    assert response.status_code == 403 and response.json()["error"]["code"] == "self_grant_forbidden"
    assert _events(db, "SELF_GRANT_BLOCKED")


def test_procurement_manager_not_on_the_process_cannot_read_it(world, db):
    proc, process = _setup_with_offers(db)
    clock.set_now(clock.now() + timedelta(days=4))
    proc = ApiClient("proc@example.com")
    assert proc.post(f"/api/v1/processes/{process['id']}/opening/requests").status_code == 200
    other = ApiClient("proc2@example.com")
    response = other.get(f"/api/v1/processes/{process['id']}/comparison")
    assert response.status_code == 403 and response.json()["error"]["code"] == "not_a_participant"


def test_cannot_open_before_deadline(world, db):
    proc, process = _setup_with_offers(db)
    response = proc.post(f"/api/v1/processes/{process['id']}/opening/requests")
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "opening_policy_failed"
    assert any(r["rule"] == "time" and r["status"] == "FAIL" for r in body["details"]["results"])
    events = _events(db, "EARLY_OPEN_ATTEMPT", process["id"])
    assert events and events[0].severity == "CRITICAL"


def test_opening_opens_all_together_and_notifies_every_submitter(world, db, mail):
    proc, process = _setup_with_offers(db, 3)
    clock.set_now(clock.now() + timedelta(days=4))
    proc = ApiClient("proc@example.com")
    result = proc.post(f"/api/v1/processes/{process['id']}/opening/requests").json()
    assert result["status"] == "EXECUTED" and result["opened_submissions"] == 3
    subs = db.execute(select(Submission).where(Submission.process_id == uuid.UUID(process["id"]))).scalars().all()
    assert {s.status for s in subs} == {"OPENED"} and len({s.opened_at for s in subs}) == 1
    assert len(_events(db, "VAULT_OPENED", process["id"])) == 1
    notes = db.execute(select(Notification).where(Notification.event_type == "VAULT_OPENED")).scalars().all()
    assert sorted(n.recipient_email for n in notes) == ["computers@example.com", "desktop@example.com",
                                                        "rootit@example.com"]
    body = notes[0].body
    assert "80,000" not in body and "Company" not in body   # no competitor data
    comparison = proc.get(f"/api/v1/processes/{process['id']}/comparison").json()
    assert len(comparison["rows"]) == 3 and comparison["ranking"] is None
    assert comparison["rows"][0]["values"]["vat_agorot"] == round(comparison["rows"][0]["values"]["price_before_vat_agorot"] * 0.18)
    assert len(_events(db, "PROPOSAL_VIEWED", process["id"])) == 3


def test_only_latest_version_counts_and_submitting_after_deadline_fails(world, db):
    proc = ApiClient("proc@example.com")
    process = create_rfq(proc, db)
    supplier = ApiClient("desktop@example.com")
    assert submit_offer(supplier, process["id"], 90000).status_code == 200
    assert submit_offer(supplier, process["id"], 85000).status_code == 200
    receipt = supplier.get(f"/api/v1/processes/{process['id']}/submission").json()
    assert receipt["current_version"]["version_no"] == 2 and len(receipt["superseded_versions"]) == 1
    clock.set_now(clock.now() + timedelta(days=4))
    proc = ApiClient("proc@example.com")
    supplier = ApiClient("desktop@example.com")
    late = submit_offer(supplier, process["id"], 70000)
    assert late.status_code == 409 and late.json()["error"]["code"] == "deadline_passed"
    proc.post(f"/api/v1/processes/{process['id']}/opening/requests")
    rows = proc.get(f"/api/v1/processes/{process['id']}/comparison").json()["rows"]
    assert [r["values"]["price_before_vat_agorot"] for r in rows] == [8_500_000]


def test_required_document_and_file_type_enforced_server_side(world, db):
    process = create_rfq(ApiClient("proc@example.com"), db)
    supplier = ApiClient("desktop@example.com")
    no_files = supplier.post(f"/api/v1/processes/{process['id']}/submission",
                             data={"payload": '{"price_before_vat_agorot": 100, "delivery_days": 1, "warranty_months": 1}'})
    assert no_files.status_code == 422 and no_files.json()["error"]["code"] == "missing_documents"
    fake_pdf = supplier.post(
        f"/api/v1/processes/{process['id']}/submission",
        data={"payload": '{"price_before_vat_agorot": 100, "delivery_days": 1, "warranty_months": 1}', "kinds": ["proposal"]},
        files=[("files", ("offer.pdf", b"MZ\x90\x00 not a pdf", "application/pdf"))])
    assert fake_pdf.status_code == 422 and fake_pdf.json()["error"]["code"] == "file_content_mismatch"


def test_modified_file_fails_integrity_and_is_blocked(world, db):
    proc, process = _setup_with_offers(db, 2)
    stored = db.execute(select(StoredFile).where(StoredFile.encrypted.is_(True))).scalars().first()
    storage = get_storage()
    tampered = bytearray(storage.get(stored.storage_key))
    tampered[-1] ^= 0x01
    storage.put(stored.storage_key, bytes(tampered))
    clock.set_now(clock.now() + timedelta(days=4))
    proc = ApiClient("proc@example.com")
    result = proc.post(f"/api/v1/processes/{process['id']}/opening/requests").json()
    assert result["status"] == "EXECUTED" and len(result["integrity_failures"]) == 1
    failures = _events(db, "FILE_INTEGRITY_FAILURE", process["id"])
    assert failures and failures[0].severity == "CRITICAL"
    db.expire_all()
    doc_row = next(r for r in proc.get(f"/api/v1/processes/{process['id']}/comparison").json()["rows"]
                   if any(d["integrity"] == "FAILED" for d in r["documents"]))
    bad_doc = next(d for d in doc_row["documents"] if d["integrity"] == "FAILED")
    response = proc.get(f"/api/v1/submissions/{doc_row['submission_id']}/documents/{bad_doc['id']}")
    assert response.status_code == 403 and response.json()["error"]["code"] == "file_integrity_failure"
    # An intact document downloads and matches its recorded hash.
    good_row = next(r for r in proc.get(f"/api/v1/processes/{process['id']}/comparison").json()["rows"]
                    if r["submission_id"] != doc_row["submission_id"])
    good = good_row["documents"][0]
    download = proc.get(f"/api/v1/submissions/{good_row['submission_id']}/documents/{good['id']}")
    import hashlib

    assert download.status_code == 200 and hashlib.sha256(download.content).hexdigest() == good["sha256"]
    assert _events(db, "PROPOSAL_DOWNLOADED", process["id"])


def test_decision_requires_reason_and_protocol_then_close(world, db):
    proc, process = _setup_with_offers(db, 2)
    pid = process["id"]
    assert proc.post(f"/api/v1/processes/{pid}/decision",
                     json={"decision_type": "NO_AWARD", "reason": "too early to decide"}).status_code == 409
    clock.set_now(clock.now() + timedelta(days=4))
    proc = ApiClient("proc@example.com")
    proc.post(f"/api/v1/processes/{pid}/opening/requests")
    rows = proc.get(f"/api/v1/processes/{pid}/comparison").json()["rows"]
    short = proc.post(f"/api/v1/processes/{pid}/decision",
                      json={"decision_type": "AWARD", "selected_submission_id": rows[0]["submission_id"], "reason": "ok"})
    assert short.status_code == 422
    assert proc.post(f"/api/v1/processes/{pid}/close").status_code == 409
    decided = proc.post(f"/api/v1/processes/{pid}/decision",
                        json={"decision_type": "AWARD", "selected_submission_id": rows[1]["submission_id"],
                              "reason": "Lowest price meeting all requirements"})
    assert decided.status_code == 200 and decided.json()["status"] == "DECIDED"
    assert proc.post(f"/api/v1/processes/{pid}/close").json()["error"]["code"] == "protocol_required"
    protocol = proc.post(f"/api/v1/processes/{pid}/protocols", json={"locale": "he"}).json()
    html = proc.get(f"/api/v1/protocols/{protocol['id']}/html")
    assert html.status_code == 200 and "Lowest price meeting all requirements" in html.text and 'dir="rtl"' in html.text
    assert proc.post(f"/api/v1/processes/{pid}/close").json()["status"] == "CLOSED"
    # The auditor reads the protocol but not proposal content.
    auditor = ApiClient("auditor@example.com")
    assert auditor.get(f"/api/v1/protocols/{protocol['id']}/html").status_code == 200
    assert auditor.get(f"/api/v1/processes/{pid}/comparison").status_code == 403


def test_notification_failure_does_not_roll_back_submission(world, db, mail):
    process = create_rfq(ApiClient("proc@example.com"), db)
    mail.fail = True
    response = submit_offer(ApiClient("desktop@example.com"), process["id"])
    assert response.status_code == 200
    stats = notifications.deliver_pending(db)
    assert stats["sent"] == 0 and stats["failed"] > 0
    assert db.execute(select(Submission).where(Submission.status == "SUBMITTED")).scalar_one()
    assert _events(db, "NOTIFICATION_FAILED")
    mail.fail = False
    clock.set_now(clock.now() + timedelta(minutes=2))
    assert notifications.deliver_pending(db)["sent"] > 0


def test_csrf_token_required_for_state_changes(world, db):
    client = ApiClient("proc@example.com")
    client.csrf = "wrong"
    response = client.post("/api/v1/processes", json={})
    assert response.status_code == 403 and response.json()["error"]["code"] == "csrf_failed"


def test_granting_business_role_alerts_oversight(world, db, mail):
    admin = ApiClient("admin@example.com")
    newcomer = make_staff(db, "new@example.com", "New", [])
    response = admin.post(f"/api/v1/admin/users/{newcomer.id}/roles",
                          json={"role_key": "procurement_manager", "reason": "joined procurement"})
    assert response.status_code == 200
    alerts = db.execute(select(Notification).where(Notification.event_type == "SECURITY_ALERT")).scalars().all()
    assert any(n.recipient_email == "auditor@example.com" for n in alerts)
