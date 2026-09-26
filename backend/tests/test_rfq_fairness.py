"""Distribution fairness: the system chooses recipients, never a person."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core import clock
from app.models import DistributionRecipient, DistributionSnapshot
from app.services import notifications
from tests.conftest import ApiClient, cat, create_rfq, make_supplier


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


def test_publisher_cannot_exclude_an_eligible_supplier(world, db):
    client = ApiClient("proc@example.com")
    draft = create_rfq(client, db, publish=False)
    excluded = str(world["suppliers"]["desktop"].id)
    for body in ({"exclude_supplier_ids": [excluded]}, {"recipients": [excluded]}, {"supplier_ids": []}):
        response = client.post(f"/api/v1/processes/{draft['id']}/publish", json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
    # Publishing with the only accepted body still reaches everyone, including the one we tried to drop.
    published = client.post(f"/api/v1/processes/{draft['id']}/publish", json={}).json()
    assert world["suppliers"]["desktop"].id in _recipient_ids(db, uuid.UUID(published["id"]))
    # And no route exists to remove a recipient afterwards.
    routes = {(r.path, m) for r in client.client.app.routes for m in getattr(r, "methods", [])}
    assert not any("recipient" in path and method in ("DELETE", "PATCH", "PUT") for path, method in routes)


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
    assert fairness["manual_changes_possible"] is False


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
    from tests.conftest import submit_offer

    response = submit_offer(outsider, process["id"])
    assert response.status_code == 403 and response.json()["error"]["code"] == "not_invited"
