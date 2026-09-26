"""Distribution fairness: the system chooses recipients, never a person."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core import clock
from app.models import AuditEvent, DistributionRecipient, DistributionSnapshot
from app.services import notifications
from tests.conftest import ApiClient, cat, create_rfq, make_supplier, submit_offer


def _recipient_ids(db, process_id):
    return {r.supplier_id for r in db.execute(
        select(DistributionRecipient).where(DistributionRecipient.process_id == process_id)).scalars()}


def test_all_matching_suppliers_receive_a_distribution_record(world, db):
    s = world["suppliers"]
    process = create_rfq(ApiClient("proc@example.com"), db)
    recipients = _recipient_ids(db, uuid.UUID(process["id"]))
    assert recipients == {s["root_it"].id, s["computers"].id, s["desktop"].id, s["desktop_ar"].id}
    assert process["publication"]["distribution"]["recipient_count"] == 4


def test_supplier_outside_category_or_inactive_is_not_invited(world, db):
    s = world["suppliers"]
    process = create_rfq(ApiClient("proc@example.com"), db)
    recipients = _recipient_ids(db, uuid.UUID(process["id"]))
    assert s["networking"].id not in recipients      # sibling branch under IT
    assert s["lighting"].id not in recipients        # unrelated category
    assert s["inactive"].id not in recipients        # not active


def test_exclusion_at_publication_requires_reason_and_is_recorded(world, db):
    client = ApiClient("proc@example.com")
    draft = create_rfq(client, db, publish=False)
    excluded = str(world["suppliers"]["desktop"].id)
    no_reason = client.post(f"/api/v1/processes/{draft['id']}/publish", json={"excluded_supplier_ids": [excluded]})
    assert no_reason.status_code == 422 and no_reason.json()["error"]["code"] == "reason_required"
    unknown_field = client.post(f"/api/v1/processes/{draft['id']}/publish", json={"recipients": [excluded]})
    assert unknown_field.status_code == 422
    published = client.post(f"/api/v1/processes/{draft['id']}/publish", json={
        "excluded_supplier_ids": [excluded], "change_reason": "Supplier is under a framework dispute"}).json()
    pid = uuid.UUID(published["id"])
    assert world["suppliers"]["desktop"].id not in _recipient_ids(db, pid)
    fairness = client.get(f"/api/v1/processes/{pid}/distribution").json()
    assert fairness["excluded_at_publication"][0]["supplier_id"] == excluded
    assert fairness["excluded_at_publication"][0]["reason"] == "Supplier is under a framework dispute"
    assert db.execute(select(AuditEvent).where(AuditEvent.event_type == "DISTRIBUTION_EDITED")).scalars().first()
    blocked = submit_offer(ApiClient("desktop@example.com"), published["id"])
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "not_invited"


def test_distribution_cannot_be_edited_where_the_type_forbids_it(world, db, monkeypatch):
    from app.processes.rfq import RFQProcess

    monkeypatch.setattr(RFQProcess, "distribution_editable", False)
    client = ApiClient("proc@example.com")
    draft = create_rfq(client, db, publish=False)
    response = client.post(f"/api/v1/processes/{draft['id']}/publish", json={
        "excluded_supplier_ids": [str(world["suppliers"]["desktop"].id)], "change_reason": "not allowed here"})
    assert response.status_code == 403 and response.json()["error"]["code"] == "distribution_not_editable"


def test_add_and_remove_after_publication(world, db):
    client = ApiClient("proc@example.com")
    process = create_rfq(client, db)
    pid = process["id"]
    desktop, networking = world["suppliers"]["desktop"], world["suppliers"]["networking"]
    assert client.post(f"/api/v1/processes/{pid}/distribution/recipients/{desktop.id}/remove",
                       json={"reason": "x"}).status_code == 422
    assert client.post(f"/api/v1/processes/{pid}/distribution/recipients/{desktop.id}/remove",
                       json={"reason": "Duplicate company registration"}).status_code == 200
    assert submit_offer(ApiClient("desktop@example.com"), pid).json()["error"]["code"] == "not_invited"
    assert client.post(f"/api/v1/processes/{pid}/distribution/recipients",
                       json={"supplier_id": str(networking.id), "reason": "Also supplies desktops"}).status_code == 200
    assert submit_offer(ApiClient("networking@example.com"), pid).status_code == 200
    kinds = [x.kind for x in db.execute(select(DistributionSnapshot).where(
        DistributionSnapshot.process_id == uuid.UUID(pid)).order_by(DistributionSnapshot.created_at)).scalars()]
    assert kinds == ["INITIAL", "MANUAL"]
    fairness = client.get(f"/api/v1/processes/{pid}/distribution").json()
    assert fairness["stats"]["manually_added"] == 1 and fairness["stats"]["manually_removed"] == 1
    removed = next(r for r in fairness["recipients"] if r["supplier_id"] == str(desktop.id))
    assert removed["removed"] and removed["removal_reason"] == "Duplicate company registration"
    response = client.post(f"/api/v1/processes/{pid}/distribution/recipients/{networking.id}/remove",
                           json={"reason": "Changed my mind"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "supplier_already_submitted"
    other = ApiClient("proc2@example.com")
    assert other.post(f"/api/v1/processes/{pid}/distribution/recipients",
                      json={"supplier_id": str(desktop.id), "reason": "Restore it please"}).status_code == 403


def test_preview_matches_publication_and_is_not_editable(world, db):
    client = ApiClient("proc@example.com")
    preview = client.post("/api/v1/distribution/preview",
                          json={"category_ids": [str(cat(db, "it.computers.desktop").id)]}).json()
    assert preview["count"] == 4 and preview["editable"] is False
    process = create_rfq(client, db)
    assert process["publication"]["distribution"]["recipient_count"] == preview["count"]


def test_every_recipient_gets_email_and_in_app_notification(world, db, mail):
    process = create_rfq(ApiClient("proc@example.com"), db)
    notifications.deliver_pending(db)
    invitations = [(to, subject) for to, subject, body in mail.sent if "/invite/?token=" in body]
    invited = [to for to, _ in invitations]
    assert sorted(invited) == sorted(["rootit@example.com", "computers@example.com", "desktop@example.com",
                                      "desktopar@example.com"])
    arabic = next(subject for to, subject in invitations if to == "desktopar@example.com")
    assert "طلب عرض أسعار" in arabic
    fairness = ApiClient("proc@example.com").get(f"/api/v1/processes/{process['id']}/distribution").json()
    assert fairness["stats"]["eligible"] == 4 and fairness["stats"]["delivered"] == 4
    assert fairness["manual_changes_possible"] is True and fairness["stats"]["manually_removed"] == 0


def test_snapshot_is_immutable_and_late_registrant_gets_supplemental_snapshot(world, db):
    process = create_rfq(ApiClient("proc@example.com"), db)
    pid = uuid.UUID(process["id"])
    initial = db.execute(select(DistributionSnapshot).where(DistributionSnapshot.process_id == pid)).scalar_one()
    clock.set_now(clock.now() + timedelta(hours=1))
    late = make_supplier(db, "latecomer", ["it.computers.desktop"])
    snapshots = db.execute(select(DistributionSnapshot).where(DistributionSnapshot.process_id == pid)
                           .order_by(DistributionSnapshot.created_at)).scalars().all()
    assert [s.kind for s in snapshots] == ["INITIAL", "SUPPLEMENTAL"]
    assert snapshots[0].snapshot_hash == initial.snapshot_hash and snapshots[0].recipient_count == 4
    assert late.id in _recipient_ids(db, pid)


def test_supplier_outside_distribution_cannot_submit_or_see_process(world, db):
    process = create_rfq(ApiClient("proc@example.com"), db)
    outsider = ApiClient("networking@example.com")
    assert outsider.get(f"/api/v1/processes/{process['id']}").status_code == 404
    response = submit_offer(outsider, process["id"])
    assert response.status_code == 403 and response.json()["error"]["code"] == "not_invited"
