"""Test harness: a fresh SQLite database, storage directory and KMS key per
test session; the clock is frozen per test; mail goes to an in-memory
transport that can be told to fail."""
from __future__ import annotations

import base64
import os
import secrets
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="bdp-tests-"))
os.environ.update({
    "ENVIRONMENT": "test",
    # TEST_DATABASE_URL runs the suite against PostgreSQL; the database is wiped per test.
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(_TMP / 'test.db').as_posix()}",
    "STORAGE_DIR": str(_TMP / "storage"),
    "VAULT_MASTER_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
    "MAIL_BACKEND": "file",
    "MAIL_OUTBOX_DIR": str(_TMP / "outbox"),
    "DEMO_MODE": "false",
    "REDIS_URL": "",
    "PUBLIC_BASE_URL": "http://testserver",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import db as db_module  # noqa: E402
from app import db_guards  # noqa: E402
from app.adapters.mail import set_mail_transport  # noqa: E402
from app.core import clock  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, User  # noqa: E402
from app.seed.baseline import seed_baseline  # noqa: E402
from app.services import suppliers as supplier_service  # noqa: E402
from app.services.suppliers import default_organization, grant_role  # noqa: E402

PASSWORD = "Correct-Horse-9"
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


class MemoryMail:
    def __init__(self):
        self.sent = []
        self.fail = False

    def send(self, to, subject, body):
        if self.fail:
            raise ConnectionError("SMTP relay unavailable")
        self.sent.append((to, subject, body))
        return f"<{len(self.sent)}@test>"


@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    yield
    db_module.engine.dispose()
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture()
def mail():
    transport = MemoryMail()
    set_mail_transport(transport)
    yield transport
    set_mail_transport(None)


@pytest.fixture()
def db(mail):
    db_module.engine.dispose()
    with db_module.engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            conn.exec_driver_sql("DROP SCHEMA public CASCADE")
            conn.exec_driver_sql("CREATE SCHEMA public")
        else:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            db_guards.uninstall(conn)
            Base.metadata.drop_all(conn)
        conn.commit()
    Base.metadata.create_all(db_module.engine)
    with db_module.engine.begin() as conn:
        db_guards.install(conn)
    clock.set_now(T0)
    session = db_module.SessionLocal()
    seed_baseline(session)
    yield session
    session.close()
    clock.set_now(None)


def cat(db, key):
    return db.execute(select(Category).where(Category.key == key)).scalar_one()


def make_staff(db, email, name, roles):
    org = default_organization(db)
    user = User(organization_id=org.id, email=email, full_name=name, kind="staff",
                password_hash=hash_password(PASSWORD), locale="he")
    db.add(user)
    db.flush()
    for role in roles:
        grant_role(db, user, role, org.id, None, "test")
    db.commit()
    return user


_counter = {"n": 0}


def make_supplier(db, slug, category_keys, status="ACTIVE", locale="he"):
    _counter["n"] += 1
    supplier = supplier_service.register(db, {
        "company_name": f"Company {slug}", "company_number": f"5{_counter['n']:08d}",
        "contact_name": f"Contact {slug}", "email": f"{slug}@example.com", "phone": "04-6000000",
        "password": PASSWORD, "category_ids": [cat(db, k).id for k in category_keys], "locale": locale,
    }, None)
    supplier.status = status
    db.commit()
    return supplier


class ApiClient:
    """TestClient that signs in and sends the CSRF header like the frontend does."""

    def __init__(self, email=None, ip="10.20.0.5"):
        self.client = TestClient(app, client=(ip, 5000))
        self.csrf = None
        if email:
            response = self.client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert response.status_code == 200, response.text
            self.csrf = response.json()["csrf_token"]

    def _headers(self, kwargs):
        headers = kwargs.pop("headers", {}) or {}
        if self.csrf:
            headers.setdefault("X-CSRF-Token", self.csrf)
        return headers

    def get(self, url, **kwargs):
        return self.client.get(url, **kwargs)

    def post(self, url, **kwargs):
        return self.client.post(url, headers=self._headers(kwargs), **kwargs)

    def patch(self, url, **kwargs):
        return self.client.patch(url, headers=self._headers(kwargs), **kwargs)

    def put(self, url, **kwargs):
        return self.client.put(url, headers=self._headers(kwargs), **kwargs)

    def delete(self, url, **kwargs):
        return self.client.delete(url, headers=self._headers(kwargs), **kwargs)


def pdf_bytes(label="x"):
    from app.seed.demo import _pdf

    return _pdf(label)


@pytest.fixture()
def world(db):
    """Staff, suppliers across the category tree, and a published desktop RFQ."""
    staff = {
        "procurement": make_staff(db, "proc@example.com", "Procurement", ["procurement_manager"]),
        "procurement_other": make_staff(db, "proc2@example.com", "Other procurement", ["procurement_manager"]),
        "admin": make_staff(db, "admin@example.com", "Admin", ["system_admin"]),
        "auditor": make_staff(db, "auditor@example.com", "Auditor", ["auditor"]),
    }
    sup = {
        "root_it": make_supplier(db, "rootit", ["it"]),
        "computers": make_supplier(db, "computers", ["it.computers"]),
        "desktop": make_supplier(db, "desktop", ["it.computers.desktop"]),
        "desktop_ar": make_supplier(db, "desktopar", ["it.computers.desktop"], locale="ar"),
        "networking": make_supplier(db, "networking", ["it.networking"]),
        "lighting": make_supplier(db, "lighting", ["electric.lighting"]),
        "inactive": make_supplier(db, "inactive", ["it.computers.desktop"], status="INACTIVE"),
    }
    return {"staff": staff, "suppliers": sup}


def create_rfq(client: ApiClient, db, category_key="it.computers.desktop", deadline=None, publish=True,
               opening_mode="sealed_after_deadline", publish_body=None):
    deadline = deadline or (clock.now() + timedelta(days=3))
    response = client.post("/api/v1/processes", json={
        "process_type": "rfq", "title": "רכישת 20 מחשבים נייחים", "description": "desktops",
        "category_ids": [str(cat(db, category_key).id)], "submission_deadline": deadline.isoformat(),
        "details": {"quantity": 20, "unit": "יח'", "technical_specification": "i5, 16GB",
                    "opening_mode": opening_mode},
        "contact_email": "proc@example.com",
    })
    assert response.status_code == 200, response.text
    process = response.json()
    if publish:
        response = client.post(f"/api/v1/processes/{process['id']}/publish", json=publish_body or {})
        assert response.status_code == 200, response.text
        process = response.json()
    return process


def submit_offer(client: ApiClient, process_id, price_shekels=80000, extra_files=()):
    files = [("files", ("offer.pdf", pdf_bytes("offer"), "application/pdf"))]
    kinds = ["proposal"]
    for kind, name, data in extra_files:
        files.append(("files", (name, data, "application/octet-stream")))
        kinds.append(kind)
    return client.post(
        f"/api/v1/processes/{process_id}/submission",
        data={"payload": '{"price_before_vat_agorot": %d, "delivery_days": 21, "warranty_months": 36, '
                         '"payment_terms": "net 30"}' % (price_shekels * 100), "kinds": kinds},
        files=files,
    )
