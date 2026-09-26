from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import client_ip, current_context, set_session_cookies
from app.api.schemas import (
    SupplierCategoriesBody,
    SupplierDocumentMeta,
    SupplierRegistration,
    SupplierStatusBody,
    SupplierUpdate,
)
from app.core import clock
from app.core.errors import Forbidden, Invalid, NotFound
from app.db import get_db
from app.models import Supplier
from app.services import authorization, identity, reporting, suppliers
from app.services.categories import breadcrumb
from app.services.identity import AuthContext

router = APIRouter(tags=["suppliers"])


def supplier_view(db: Session, supplier: Supplier, locale: str = "he", include_documents: bool = True) -> dict:
    today = clock.now().date()
    view = {
        "id": str(supplier.id), "company_name": supplier.company_name, "company_number": supplier.company_number,
        "contact_name": supplier.contact_name, "email": supplier.email, "phone": supplier.phone,
        "address": supplier.address, "city": supplier.city, "website": supplier.website,
        "description": supplier.description, "service_regions": supplier.service_regions or [],
        "status": supplier.status, "notify_email": supplier.notify_email, "notify_in_app": supplier.notify_in_app,
        "preferred_locale": supplier.preferred_locale, "registered_at": supplier.registered_at.isoformat(),
        "updated_at": supplier.updated_at.isoformat(),
        "categories": [
            {"id": str(sc.category_id), "path": breadcrumb(db, sc.category, locale)} for sc in supplier.categories
        ],
    }
    if include_documents:
        view["documents"] = [
            {"id": str(d.id), "doc_type": d.doc_type, "title": d.title,
             "issued_on": d.issued_on.isoformat() if d.issued_on else None,
             "expires_on": d.expires_on.isoformat() if d.expires_on else None,
             "expired": bool(d.expires_on and d.expires_on < today),
             "filename": d.file.original_filename, "sha256": d.file.sha256}
            for d in supplier.documents
        ]
    return view


def _own_supplier(db: Session, ctx: AuthContext) -> Supplier:
    authorization.require(ctx, "supplier.self")
    if ctx.supplier_id is None:
        raise Forbidden("no_supplier_profile", "This account is not linked to a supplier")
    return suppliers.get_with_relations(db, ctx.supplier_id)


@router.post("/suppliers/register")
def register(body: SupplierRegistration, request: Request, response: Response, db: Session = Depends(get_db)):
    data = body.model_dump()
    supplier = suppliers.register(db, data, client_ip(request))
    db.commit()
    token, csrf, _ = identity.login(db, data["email"], data["password"], client_ip(request),
                                    request.headers.get("user-agent"))
    set_session_cookies(response, token, csrf)
    return {"supplier_id": str(supplier.id), "csrf_token": csrf}


@router.get("/suppliers/me")
def my_profile(ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    return supplier_view(db, _own_supplier(db, ctx), ctx.user.locale)


@router.patch("/suppliers/me")
def update_profile(body: SupplierUpdate, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    supplier = _own_supplier(db, ctx)
    suppliers.update_profile(db, supplier, body.model_dump(exclude_none=True), ctx.actor())
    db.commit()
    return supplier_view(db, supplier, ctx.user.locale)


@router.put("/suppliers/me/categories")
def set_categories(body: SupplierCategoriesBody, ctx: AuthContext = Depends(current_context),
                   db: Session = Depends(get_db)):
    supplier = _own_supplier(db, ctx)
    invited = suppliers.set_categories(db, supplier, body.category_ids, ctx.actor())
    db.commit()
    return {"new_invitations": invited, "supplier": supplier_view(db, suppliers.get_with_relations(db, supplier.id),
                                                                  ctx.user.locale)}


@router.post("/suppliers/me/documents")
async def upload_document(
    meta: str = Form(...),
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(current_context),
    db: Session = Depends(get_db),
):
    try:
        parsed = SupplierDocumentMeta.model_validate(json.loads(meta))
    except (ValueError, ValidationError) as exc:
        raise Invalid("validation_error", "Invalid document details", {"errors": str(exc)[:500]}) from exc
    supplier = _own_supplier(db, ctx)
    data = await file.read()
    doc = suppliers.add_document(db, supplier, doc_type=parsed.doc_type, title=parsed.title,
                                 filename=file.filename or "file", data=data, issued_on=parsed.issued_on,
                                 expires_on=parsed.expires_on, actor=ctx.actor())
    db.commit()
    return {"id": str(doc.id)}


@router.get("/suppliers/me/opportunities")
def opportunities(ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    return reporting.supplier_opportunities(db, ctx)


@router.get("/suppliers")
def search(q: str = "", status: Optional[str] = None, category_id: Optional[uuid.UUID] = None, limit: int = 50,
           offset: int = 0, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    authorization.require(ctx, "supplier.registry.read")
    rows, total = suppliers.search(db, q, status, category_id, min(max(limit, 1), 200), max(offset, 0))
    today = clock.now().date()
    return {
        "total": total,
        "items": [
            {"id": str(s.id), "company_name": s.company_name, "company_number": s.company_number, "city": s.city,
             "status": s.status, "registered_at": s.registered_at.isoformat(),
             "category_count": len(s.categories),
             "categories": [sc.category.name(ctx.user.locale) for sc in s.categories][:6],
             "expired_documents": sum(1 for d in s.documents if d.expires_on and d.expires_on < today)}
            for s in rows
        ],
    }


@router.get("/suppliers/{supplier_id}")
def get_supplier(supplier_id: uuid.UUID, ctx: AuthContext = Depends(current_context), db: Session = Depends(get_db)):
    authorization.require(ctx, "supplier.registry.read")
    supplier = suppliers.get_with_relations(db, supplier_id)
    return supplier_view(db, supplier, ctx.user.locale)


@router.patch("/suppliers/{supplier_id}/status")
def set_status(supplier_id: uuid.UUID, body: SupplierStatusBody, ctx: AuthContext = Depends(current_context),
               db: Session = Depends(get_db)):
    authorization.require(ctx, "supplier.registry.manage")
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFound("supplier")
    suppliers.set_status(db, supplier, body.status, body.reason, ctx.actor())
    db.commit()
    return {"ok": True}

