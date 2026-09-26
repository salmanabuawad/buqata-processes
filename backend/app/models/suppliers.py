from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONType
from app.models.base import created_at_column, uuid_pk


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("categories.id"))
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name_he: Mapped[str] = mapped_column(String(160))
    name_ar: Mapped[str] = mapped_column(String(160))
    name_en: Mapped[str] = mapped_column(String(160))
    path: Mapped[str] = mapped_column(String(1000), index=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def name(self, locale: str) -> str:
        return getattr(self, f"name_{locale}", None) or self.name_he


class StoredFile(Base):
    __tablename__ = "stored_files"

    id: Mapped[uuid.UUID] = uuid_pk()
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    integrity_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = created_at_column()


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    company_name: Mapped[str] = mapped_column(String(200))
    company_number: Mapped[str] = mapped_column(String(20), unique=True)
    contact_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str] = mapped_column(String(40))
    address: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    service_regions: Mapped[list] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    notify_email: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_in_app: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_locale: Mapped[str] = mapped_column(String(5), default="he")
    registered_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = created_at_column()

    categories: Mapped[List["SupplierCategory"]] = relationship(
        back_populates="supplier", cascade="all, delete-orphan"
    )
    contacts: Mapped[List["SupplierContact"]] = relationship(back_populates="supplier")
    documents: Mapped[List["SupplierDocument"]] = relationship(back_populates="supplier")


class SupplierContact(Base):
    __tablename__ = "supplier_contacts"

    id: Mapped[uuid.UUID] = uuid_pk()
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    title: Mapped[str] = mapped_column(String(120), default="")

    supplier: Mapped[Supplier] = relationship(back_populates="contacts")


class SupplierCategory(Base):
    __tablename__ = "supplier_categories"

    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), primary_key=True)
    added_at: Mapped[datetime] = created_at_column()

    supplier: Mapped[Supplier] = relationship(back_populates="categories")
    category: Mapped[Category] = relationship()


class SupplierDocument(Base):
    __tablename__ = "supplier_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    stored_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stored_files.id"))
    issued_on: Mapped[Optional[date]] = mapped_column(Date)
    expires_on: Mapped[Optional[date]] = mapped_column(Date, index=True)
    uploaded_at: Mapped[datetime] = created_at_column()

    supplier: Mapped[Supplier] = relationship(back_populates="documents")
    file: Mapped[StoredFile] = relationship()
