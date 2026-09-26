"""Request bodies. Every model forbids unknown fields — an attempt to smuggle,
say, an exclusion list into publication is rejected, not ignored."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Locale = Literal["he", "ar", "en"]


class LoginBody(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class DemoLoginBody(Strict):
    user_id: uuid.UUID


class MeUpdate(Strict):
    locale: Optional[Locale] = None
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=40)


class SupplierRegistration(Strict):
    company_name: str = Field(min_length=2, max_length=200)
    company_number: str = Field(pattern=r"^\d{8,9}$")
    contact_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=40)
    password: str = Field(min_length=10, max_length=200)
    address: str = Field(default="", max_length=300)
    city: str = Field(default="", max_length=120)
    website: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=3000)
    service_regions: List[str] = Field(default_factory=list, max_length=20)
    category_ids: List[uuid.UUID] = Field(min_length=1, max_length=60)
    locale: Locale = "he"
    accept_terms: bool

    @field_validator("accept_terms")
    @classmethod
    def _must_accept(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Terms must be accepted")
        return value


class SupplierUpdate(Strict):
    company_name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    contact_name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    phone: Optional[str] = Field(default=None, min_length=7, max_length=40)
    address: Optional[str] = Field(default=None, max_length=300)
    city: Optional[str] = Field(default=None, max_length=120)
    website: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = Field(default=None, max_length=3000)
    service_regions: Optional[List[str]] = Field(default=None, max_length=20)
    notify_email: Optional[bool] = None
    notify_in_app: Optional[bool] = None
    preferred_locale: Optional[Locale] = None


class SupplierCategoriesBody(Strict):
    category_ids: List[uuid.UUID] = Field(min_length=1, max_length=60)


class SupplierStatusBody(Strict):
    status: Literal["ACTIVE", "INACTIVE", "SUSPENDED"]
    reason: str = Field(min_length=5, max_length=500)


class CategoryCreate(Strict):
    key: str = Field(min_length=2, max_length=80)
    name_he: str = Field(min_length=1, max_length=160)
    name_ar: str = Field(min_length=1, max_length=160)
    name_en: str = Field(min_length=1, max_length=160)
    parent_id: Optional[uuid.UUID] = None
    sort_order: int = 0


class CategoryUpdate(Strict):
    name_he: Optional[str] = Field(default=None, min_length=1, max_length=160)
    name_ar: Optional[str] = Field(default=None, min_length=1, max_length=160)
    name_en: Optional[str] = Field(default=None, min_length=1, max_length=160)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ProcessCreate(Strict):
    process_type: str
    reference_number: Optional[str] = Field(default=None, max_length=40)
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=20000)
    category_ids: List[uuid.UUID] = Field(default_factory=list, max_length=20)
    submission_deadline: datetime
    opening_time: Optional[datetime] = None
    details: dict = Field(default_factory=dict)
    contact_name: str = Field(default="", max_length=200)
    contact_email: str = Field(default="", max_length=254)
    contact_phone: str = Field(default="", max_length=40)


class ProcessUpdate(Strict):
    title: Optional[str] = Field(default=None, min_length=3, max_length=300)
    description: Optional[str] = Field(default=None, max_length=20000)
    category_ids: Optional[List[uuid.UUID]] = Field(default=None, max_length=20)
    submission_deadline: Optional[datetime] = None
    opening_time: Optional[datetime] = None
    details: Optional[dict] = None
    contact_name: Optional[str] = Field(default=None, max_length=200)
    contact_email: Optional[str] = Field(default=None, max_length=254)
    contact_phone: Optional[str] = Field(default=None, max_length=40)


class PublishBody(Strict):
    """Deliberately empty: publication takes no recipient input."""


class CancelBody(Strict):
    reason: str = Field(min_length=5, max_length=2000)


class DistributionPreviewBody(Strict):
    category_ids: List[uuid.UUID] = Field(min_length=1, max_length=20)
    service_regions: List[str] = Field(default_factory=list, max_length=20)


class ApprovalBody(Strict):
    reason: str = Field(default="", max_length=2000)


class DecisionBody(Strict):
    decision_type: Literal["AWARD", "NO_AWARD"]
    selected_submission_id: Optional[uuid.UUID] = None
    reason: str = Field(min_length=10, max_length=5000)


class ProtocolBody(Strict):
    locale: Locale = "he"


class ParticipantBody(Strict):
    user_id: uuid.UUID
    participation: Literal["TEAM", "COMMITTEE", "OPENING_OFFICIAL", "CONTENT_ACCESS"]
    reason: str = Field(min_length=5, max_length=1000)


class StaffUserCreate(Strict):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: Optional[str] = Field(default=None, min_length=10, max_length=200)
    locale: Locale = "he"


class UserActiveBody(Strict):
    is_active: bool


class RoleGrantBody(Strict):
    role_key: str
    reason: str = Field(min_length=5, max_length=1000)


class SupplierDocumentMeta(Strict):
    doc_type: str = Field(min_length=2, max_length=60)
    title: str = Field(min_length=2, max_length=200)
    issued_on: Optional[date] = None
    expires_on: Optional[date] = None
