"""Supplier registry: self-registration, profile, categories, certificates."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core import clock
from app.core.errors import Conflict, Invalid, NotFound
from app.core.security import hash_password
from app.models import (
    Category,
    Organization,
    Role,
    Supplier,
    SupplierCategory,
    SupplierContact,
    SupplierDocument,
    User,
    UserRole,
)
from app.services import audit, distribution, documents, notifications
from app.services import categories as category_service
from app.services.audit import Actor


def default_organization(db: Session) -> Organization:
    org = db.execute(select(Organization).order_by(Organization.created_at).limit(1)).scalar_one_or_none()
    if org is None:
        raise RuntimeError("No organization configured — run `python -m app.cli seed`")
    return org


def grant_role(db: Session, user: User, role_key: str, organization_id: uuid.UUID,
               granted_by: Optional[uuid.UUID], reason: str) -> None:
    role = db.execute(select(Role).where(Role.key == role_key)).scalar_one()
    db.add(UserRole(user_id=user.id, role_id=role.id, organization_id=organization_id,
                    granted_by=granted_by, reason=reason, granted_at=clock.now()))


def register(db: Session, data: dict, ip: Optional[str], created_by: Optional[Actor] = None) -> Supplier:
    """Self-registration, or an administrator adding a supplier (`created_by`)."""
    email = data["email"].strip().lower()
    if db.execute(select(User.id).where(User.email == email)).first():
        raise Conflict("email_taken", "An account with this email already exists")
    if db.execute(select(Supplier.id).where(Supplier.company_number == data["company_number"])).first():
        raise Conflict("company_number_taken", "This company number is already registered")
    cats = category_service.get_many(db, data["category_ids"])
    if not cats:
        raise Invalid("category_required", "Choose at least one business category")
    org = default_organization(db)
    now = clock.now()
    user = User(id=uuid.uuid4(), organization_id=org.id, email=email, full_name=data["contact_name"],
                phone=data.get("phone"), kind="supplier", password_hash=hash_password(data["password"]),
                locale=data.get("locale", "he"), created_at=now)
    db.add(user)
    db.flush()
    grant_role(db, user, "supplier", org.id, created_by.user_id if created_by else None,
               "added by administrator" if created_by else "self-registration")
    supplier = Supplier(
        id=uuid.uuid4(), organization_id=org.id, company_name=data["company_name"].strip(),
        company_number=data["company_number"].strip(), contact_name=data["contact_name"].strip(),
        email=email, phone=data["phone"].strip(), address=data.get("address", ""), city=data.get("city", ""),
        website=data.get("website", ""), description=data.get("description", ""),
        service_regions=data.get("service_regions") or [], status="ACTIVE",
        preferred_locale=data.get("locale", "he"), registered_at=now, updated_at=now,
    )
    db.add(supplier)
    db.flush()
    db.add(SupplierContact(supplier_id=supplier.id, user_id=user.id, is_primary=True))
    for c in cats:
        db.add(SupplierCategory(supplier_id=supplier.id, category_id=c.id, added_at=now))
    db.flush()
    actor = created_by or Actor(user.id, "supplier", ip)
    audit.record(db, "USER_CREATED" if created_by else "USER_REGISTERED", actor,
                 metadata={"user_id": user.id, "kind": "supplier"})
    audit.record(db, "SUPPLIER_CREATED" if created_by else "SUPPLIER_REGISTERED", actor,
                 metadata={"supplier_id": supplier.id, "category_ids": sorted(str(c.id) for c in cats)})
    notifications.enqueue(
        db, "SUPPLIER_REGISTERED",
        [notifications.Recipient(user.id, email, supplier.preferred_locale, supplier.id)],
        {"company": supplier.company_name,
         "categories": ", ".join(c.name(supplier.preferred_locale) for c in cats)},
        link="/supplier/",
    )
    db.refresh(supplier)
    distribution.extend_for_supplier(db, supplier, actor)
    return supplier


def update_profile(db: Session, supplier: Supplier, changes: dict, actor: Actor, by_admin: bool = False) -> Supplier:
    allowed = {"company_name", "contact_name", "phone", "address", "city", "website", "description",
               "service_regions", "notify_email", "notify_in_app", "preferred_locale"}
    if by_admin:
        allowed.add("company_number")
        number = changes.get("company_number")
        if number and number != supplier.company_number and db.execute(
                select(Supplier.id).where(Supplier.company_number == number)).first():
            raise Conflict("company_number_taken", "This company number is already registered")
    applied = {}
    for key, value in changes.items():
        if key in allowed and value is not None and getattr(supplier, key) != value:
            setattr(supplier, key, value)
            applied[key] = value if key not in ("phone",) else "(changed)"
    if applied:
        supplier.updated_at = clock.now()
        audit.record(db, "SUPPLIER_UPDATED", actor, metadata={"supplier_id": supplier.id, "fields": sorted(applied)})
    return supplier


def set_categories(db: Session, supplier: Supplier, category_ids: List[uuid.UUID], actor: Actor) -> int:
    cats = category_service.get_many(db, category_ids)
    if not cats:
        raise Invalid("category_required", "Choose at least one business category")
    before = {sc.category_id for sc in supplier.categories}
    after = {c.id for c in cats}
    if before == after:
        return 0
    supplier.categories = [sc for sc in supplier.categories if sc.category_id in after]
    for cid in after - before:
        supplier.categories.append(SupplierCategory(category_id=cid, added_at=clock.now()))
    supplier.updated_at = clock.now()
    db.flush()
    audit.record(db, "SUPPLIER_CATEGORY_CHANGED", actor,
                 metadata={"supplier_id": supplier.id, "added": sorted(str(i) for i in after - before),
                           "removed": sorted(str(i) for i in before - after)})
    db.refresh(supplier)
    return distribution.extend_for_supplier(db, supplier, actor)


def add_document(db: Session, supplier: Supplier, *, doc_type: str, title: str, filename: str, data: bytes,
                 issued_on: Optional[date], expires_on: Optional[date], actor: Actor) -> SupplierDocument:
    upload = documents.validate_upload(filename, data, [".pdf", ".png", ".jpg", ".jpeg"])
    stored = documents.store_plain(db, upload, actor, prefix="supplier-docs")
    document = SupplierDocument(supplier_id=supplier.id, doc_type=doc_type, title=title, stored_file_id=stored.id,
                                issued_on=issued_on, expires_on=expires_on, uploaded_at=clock.now())
    db.add(document)
    db.flush()
    audit.record(db, "SUPPLIER_DOCUMENT_UPLOADED", actor,
                 metadata={"supplier_id": supplier.id, "document_id": document.id, "doc_type": doc_type,
                           "expires_on": expires_on.isoformat() if expires_on else None})
    return document


def set_status(db: Session, supplier: Supplier, status: str, reason: str, actor: Actor) -> None:
    """ARCHIVED is how a supplier is removed: the row stays (distribution snapshots and
    submissions refer to it), it leaves the registry and matching, and its sign-in is disabled."""
    if status not in ("ACTIVE", "INACTIVE", "SUSPENDED", "ARCHIVED"):
        raise Invalid("invalid_status", "Unknown supplier status")
    if status == supplier.status:
        return
    previous = supplier.status
    supplier.status = status
    supplier.updated_at = clock.now()
    if "ARCHIVED" in (status, previous):
        user_ids = select(SupplierContact.user_id).where(SupplierContact.supplier_id == supplier.id)
        for user in db.execute(select(User).where(User.id.in_(user_ids))).scalars():
            user.is_active = status != "ARCHIVED"
    audit.record(db, "SUPPLIER_STATUS_CHANGED", actor,
                 metadata={"supplier_id": supplier.id, "from": previous, "to": status, "reason": reason})
    if status == "ACTIVE":
        distribution.extend_for_supplier(db, supplier, actor)


def get_with_relations(db: Session, supplier_id: uuid.UUID) -> Supplier:
    supplier = db.execute(
        select(Supplier).where(Supplier.id == supplier_id).options(
            selectinload(Supplier.categories).selectinload(SupplierCategory.category),
            selectinload(Supplier.documents).selectinload(SupplierDocument.file),
        )
    ).scalar_one_or_none()
    if supplier is None:
        raise NotFound("supplier")
    return supplier


def search(db: Session, q: str = "", status: Optional[str] = None, category_id: Optional[uuid.UUID] = None,
           limit: int = 50, offset: int = 0):
    stmt = select(Supplier)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Supplier.company_name.ilike(like), Supplier.company_number.ilike(like),
                              Supplier.city.ilike(like)))
    if status:
        stmt = stmt.where(Supplier.status == status)
    else:
        stmt = stmt.where(Supplier.status != "ARCHIVED")
    if category_id:
        cat = db.get(Category, category_id)
        if cat is None:
            raise NotFound("category")
        sub = select(SupplierCategory.supplier_id).join(Category, Category.id == SupplierCategory.category_id).where(
            Category.path.like(f"{cat.path}%"))
        stmt = stmt.where(Supplier.id.in_(sub))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.options(selectinload(Supplier.categories).selectinload(SupplierCategory.category),
                     selectinload(Supplier.documents))
        .order_by(Supplier.company_name).limit(limit).offset(offset)
    ).scalars().all()
    return rows, total


def expiring_documents(db: Session, within_days: int = 30) -> List[SupplierDocument]:
    today = clock.now().date()
    return list(db.execute(
        select(SupplierDocument).where(
            SupplierDocument.expires_on.is_not(None),
            SupplierDocument.expires_on <= today + timedelta(days=within_days),
        ).order_by(SupplierDocument.expires_on)
    ).scalars())
