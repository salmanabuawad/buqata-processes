"""CategoryService — the multilingual category tree lives in the database."""
from __future__ import annotations

import re
import uuid
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, Invalid, NotFound
from app.models import Category
from app.services import audit
from app.services.audit import Actor

_KEY = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,79}$")


def create(db: Session, actor: Actor, *, key: str, name_he: str, name_ar: str, name_en: str,
           parent_id: Optional[uuid.UUID] = None, sort_order: int = 0) -> Category:
    if not _KEY.match(key):
        raise Invalid("invalid_category_key", "Key must be lowercase letters, digits, '.', '-' or '_'")
    if db.execute(select(Category.id).where(Category.key == key)).first():
        raise Conflict("category_key_exists", "A category with this key already exists")
    parent = None
    if parent_id:
        parent = db.get(Category, parent_id)
        if parent is None:
            raise NotFound("parent category")
    category = Category(id=uuid.uuid4(), parent_id=parent_id, key=key, name_he=name_he.strip(),
                        name_ar=name_ar.strip(), name_en=name_en.strip(), sort_order=sort_order)
    category.path = (parent.path if parent else "/") + f"{category.id}/"
    category.depth = (parent.depth + 1) if parent else 0
    db.add(category)
    db.flush()
    audit.record(db, "CATEGORY_CREATED", actor, metadata={"category_id": category.id, "key": key})
    return category


def update(db: Session, actor: Actor, category_id: uuid.UUID, changes: Dict) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise NotFound("category")
    allowed = {"name_he", "name_ar", "name_en", "sort_order", "is_active"}
    applied = {}
    for field, value in changes.items():
        if field in allowed and value is not None and getattr(category, field) != value:
            setattr(category, field, value)
            applied[field] = value
    if applied:
        audit.record(db, "CATEGORY_UPDATED", actor, metadata={"category_id": category.id, "changes": applied})
    return category


def all_categories(db: Session, include_inactive: bool = False) -> List[Category]:
    stmt = select(Category).order_by(Category.depth, Category.sort_order, Category.name_he)
    if not include_inactive:
        stmt = stmt.where(Category.is_active.is_(True))
    return list(db.execute(stmt).scalars())


def tree(db: Session, include_inactive: bool = False, supplier_counts: bool = False) -> List[dict]:
    categories = all_categories(db, include_inactive)
    counts: Dict[uuid.UUID, int] = {}
    if supplier_counts:
        from app.models import Supplier, SupplierCategory

        rows = db.execute(
            select(SupplierCategory.category_id, func.count())
            .join(Supplier, Supplier.id == SupplierCategory.supplier_id)
            .where(Supplier.status == "ACTIVE")
            .group_by(SupplierCategory.category_id)
        ).all()
        counts = {row[0]: row[1] for row in rows}
    nodes = {
        c.id: {
            "id": str(c.id), "key": c.key, "parent_id": str(c.parent_id) if c.parent_id else None,
            "name_he": c.name_he, "name_ar": c.name_ar, "name_en": c.name_en, "depth": c.depth,
            "is_active": c.is_active, "sort_order": c.sort_order,
            "direct_suppliers": counts.get(c.id, 0), "children": [],
        }
        for c in categories
    }
    roots = []
    for c in categories:
        node = nodes[c.id]
        if c.parent_id and c.parent_id in nodes:
            nodes[c.parent_id]["children"].append(node)
        elif c.parent_id is None:
            roots.append(node)
    return roots


def get_many(db: Session, ids: List[uuid.UUID]) -> List[Category]:
    if not ids:
        return []
    found = list(db.execute(select(Category).where(Category.id.in_(ids), Category.is_active.is_(True))).scalars())
    if len(found) != len(set(ids)):
        raise Invalid("unknown_category", "One or more categories do not exist or are inactive")
    return found


def breadcrumb(db: Session, category: Category, locale: str = "he") -> str:
    ids = [uuid.UUID(part) for part in category.path.strip("/").split("/") if part]
    by_id = {c.id: c for c in db.execute(select(Category).where(Category.id.in_(ids))).scalars()}
    return " → ".join(by_id[i].name(locale) for i in ids if i in by_id)
