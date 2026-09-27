"""Who may do what: administrators maintain the supplier registry, requesters
open quotation requests and see only their own."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core import clock
from app.models import AuditEvent, DistributionRecipient, User
from tests.conftest import PASSWORD, ApiClient, cat, create_rfq, make_staff


def _new_supplier(db, **overrides):
    body = {
        "company_name": "Admin Added Ltd", "company_number": "512345678", "contact_name": "Dana Cohen",
        "email": "added@example.com", "phone": "04-6111111", "password": PASSWORD,
        "category_ids": [str(cat(db, "it.computers.desktop").id)], "city": "Buq'ata",
    }
    body.update(overrides)
    return body


def test_only_the_administrator_manages_suppliers(world, db):
    procurement = ApiClient("proc@example.com")
    assert procurement.get("/api/v1/suppliers").status_code == 200
    assert procurement.post("/api/v1/suppliers", json=_new_supplier(db)).status_code == 403
    target = world["suppliers"]["desktop"].id
    assert procurement.patch(f"/api/v1/suppliers/{target}", json={"city": "Haifa"}).status_code == 403
    assert procurement.patch(f"/api/v1/suppliers/{target}/status",
                             json={"status": "ARCHIVED", "reason": "not needed"}).status_code == 403


def test_administrator_adds_edits_and_archives_a_supplier(world, db):
    admin = ApiClient("admin@example.com")
    response = admin.post("/api/v1/suppliers", json=_new_supplier(db))
    assert response.status_code == 200, response.text
    supplier = response.json()
    assert supplier["status"] == "ACTIVE"
    assert db.execute(select(AuditEvent).where(AuditEvent.event_type == "SUPPLIER_CREATED")).scalars().first()

    # The supplier signs in with the password the administrator handed over.
    ApiClient("added@example.com")

    # Company numbers stay unique; categories can change in the same edit.
    taken = world["suppliers"]["desktop"].company_number
    assert admin.patch(f"/api/v1/suppliers/{supplier['id']}",
                       json={"company_number": taken}).status_code == 409
    response = admin.patch(f"/api/v1/suppliers/{supplier['id']}", json={
        "city": "Mas'ade", "company_number": "598765432",
        "category_ids": [str(cat(db, "it.networking").id)]})
    assert response.status_code == 200, response.text
    edited = response.json()
    assert edited["city"] == "Mas'ade" and edited["company_number"] == "598765432"
    assert len(edited["categories"]) == 1

    # Archiving removes the supplier from the registry, matching and sign-in; nothing is deleted.
    response = admin.patch(f"/api/v1/suppliers/{supplier['id']}/status",
                           json={"status": "ARCHIVED", "reason": "Company closed"})
    assert response.status_code == 200, response.text
    listed = {r["id"] for r in admin.get("/api/v1/suppliers?limit=200").json()["items"]}
    assert supplier["id"] not in listed
    archived = {r["id"] for r in admin.get("/api/v1/suppliers?status=ARCHIVED").json()["items"]}
    assert supplier["id"] in archived
    login = ApiClient().client.post("/api/v1/auth/login", json={"email": "added@example.com", "password": PASSWORD})
    assert login.status_code != 200
    process = create_rfq(ApiClient("proc@example.com"), db, category_key="it.networking")
    recipients = {r.supplier_id for r in db.execute(select(DistributionRecipient).where(
        DistributionRecipient.process_id == uuid.UUID(process["id"]))).scalars()}
    assert uuid.UUID(supplier["id"]) not in recipients

    # Restoring brings the sign-in back.
    admin.patch(f"/api/v1/suppliers/{supplier['id']}/status", json={"status": "ACTIVE", "reason": "Reopened"})
    db.expire_all()
    assert db.execute(select(User).where(User.email == "added@example.com")).scalar_one().is_active


def test_requester_opens_quotation_requests_and_sees_only_their_own(world, db):
    make_staff(db, "requester@example.com", "Requester", ["requester"])
    requester = ApiClient("requester@example.com")
    procurement = ApiClient("proc@example.com")
    theirs = create_rfq(procurement, db)
    mine = create_rfq(requester, db)
    assert mine["status"] == "PUBLISHED"

    listed = {p["id"] for p in requester.get("/api/v1/processes").json()["items"]}
    assert listed == {mine["id"]}
    assert requester.get(f"/api/v1/processes/{theirs['id']}").status_code == 404
    assert requester.get(f"/api/v1/processes/{mine['id']}").json()["can"]["add_participants"] is True

    # Nothing beyond quotation requests.
    assert requester.get("/api/v1/suppliers").status_code == 403
    assert requester.get("/api/v1/dashboard/staff").status_code == 403
    assert requester.post("/api/v1/processes", json={
        "process_type": "tender", "title": "x", "submission_deadline": (clock.now() + timedelta(days=9)).isoformat(),
    }).status_code in (403, 404, 422)


def test_requester_hands_the_request_to_procurement_for_opening(world, db):
    make_staff(db, "requester@example.com", "Requester", ["requester"])
    requester = ApiClient("requester@example.com")
    process = create_rfq(requester, db)
    pid = process["id"]

    candidates = requester.get(f"/api/v1/processes/{pid}/participant-candidates").json()
    names = {c["name"] for c in candidates}
    assert "Procurement" in names
    assert not names & {"Admin", "Requester", "Auditor"}
    proc_id = next(c["user_id"] for c in candidates if c["name"] == "Procurement")
    body = {"user_id": proc_id, "participation": "TEAM", "reason": "Procurement opens and decides"}
    assert requester.post(f"/api/v1/processes/{pid}/participants", json=body).status_code == 200
    assert requester.post(f"/api/v1/processes/{pid}/participants", json=body).status_code == 409

    # The requester cannot open offers; the procurement participant can, after the deadline.
    clock.set_now(clock.now() + timedelta(days=4))
    requester = ApiClient("requester@example.com")
    assert requester.post(f"/api/v1/processes/{pid}/opening/requests").status_code == 403
    response = ApiClient("proc@example.com").post(f"/api/v1/processes/{pid}/opening/requests")
    assert response.status_code == 200, response.text
