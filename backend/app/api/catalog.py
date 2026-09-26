"""Meta, categories, admin (users and roles)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_context
from app.api.schemas import CategoryCreate, CategoryUpdate, RoleGrantBody, StaffUserCreate, UserActiveBody
from app.config import get_settings
from app.db import get_db
from app.models import ProcessType
from app.processes.registry import PLANNED_TYPES, all_definitions
from app.services import admin, authorization, categories
from app.services.identity import AuthContext

router = APIRouter()


@router.get("/health", tags=["meta"])
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}


@router.get("/meta", tags=["meta"])
def meta():
    s = get_settings()
    return {
        "environment": s.environment,
        "demo_mode": s.demo_enabled,
        "vat_rate_percent": s.vat_rate_percent,
        "timezone": s.timezone,
        "max_upload_mb": s.max_upload_mb,
    }


@router.get("/process-types", tags=["meta"])
def process_types(db: Session = Depends(get_db)):
    rows = {p.key: p for p in db.execute(select(ProcessType)).scalars()}
    result = []
    for key, definition in all_definitions().items():
        row = rows.get(key)
        result.append({
            "key": key, "names": definition.names, "available": bool(row and row.is_enabled),
            "create_permission": definition.create_permission, "timeline": definition.timeline,
            "document_requirements": [
                {"kind": r.kind, "required": r.required, "extensions": list(r.extensions), "multiple": r.multiple,
                 "names": r.names}
                for r in definition.document_requirements
            ],
        })
    for key, names in PLANNED_TYPES.items():
        result.append({"key": key, "names": names, "available": False, "planned": True})
    return result


@router.get("/categories", tags=["categories"])
def list_categories(include_inactive: bool = False, db: Session = Depends(get_db)):
    return categories.tree(db, include_inactive=include_inactive, supplier_counts=True)


@router.post("/categories", tags=["categories"])
def create_category(body: CategoryCreate, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    authorization.require(ctx, "category.manage")
    category = categories.create(db, ctx.actor(), **body.model_dump())
    db.commit()
    return {"id": str(category.id)}


@router.patch("/categories/{category_id}", tags=["categories"])
def update_category(category_id: uuid.UUID, body: CategoryUpdate, ctx: AuthContext = Depends(current_context),
                    db: Session = Depends(get_db)):
    authorization.require(ctx, "category.manage")
    categories.update(db, ctx.actor(), category_id, body.model_dump(exclude_none=True))
    db.commit()
    return {"ok": True}


@router.get("/admin/users", tags=["admin"])
def users(kind: Optional[str] = None, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    return admin.list_users(db, ctx, kind)


@router.post("/admin/users", tags=["admin"])
def create_user(body: StaffUserCreate, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    user = admin.create_staff_user(db, ctx, **body.model_dump())
    db.commit()
    return {"id": str(user.id)}


@router.patch("/admin/users/{user_id}", tags=["admin"])
def set_user_active(user_id: uuid.UUID, body: UserActiveBody, ctx: AuthContext = Depends(current_context),
                    db: Session = Depends(get_db)):
    admin.set_active(db, ctx, user_id, body.is_active)
    db.commit()
    return {"ok": True}


@router.post("/admin/users/{user_id}/roles", tags=["admin"])
def grant_role(user_id: uuid.UUID, body: RoleGrantBody, ctx: AuthContext = Depends(current_context),
               db: Session = Depends(get_db)):
    admin.grant(db, ctx, user_id, body.role_key, body.reason)
    db.commit()
    admin.flush_alerts(db)
    return {"ok": True}


@router.delete("/admin/users/{user_id}/roles/{role_key}", tags=["admin"])
def revoke_role(user_id: uuid.UUID, role_key: str, ctx: AuthContext = Depends(current_context),
                db: Session = Depends(get_db)):
    admin.revoke(db, ctx, user_id, role_key)
    db.commit()
    return {"ok": True}


@router.get("/admin/roles", tags=["admin"])
def roles(ctx: AuthContext = Depends(current_context)):
    authorization.require(ctx, "role.assign")
    return admin.roles_catalogue()
