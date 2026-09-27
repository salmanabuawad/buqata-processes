from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONType, UTCDateTime
from app.models.base import created_at_column, uuid_pk


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name_he: Mapped[str] = mapped_column(String(200))
    name_ar: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_column()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20))  # staff | supplier | applicant
    password_hash: Mapped[Optional[str]] = mapped_column(String(300))
    locale: Mapped[str] = mapped_column(String(5), default="he")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # KMS-wrapped TOTP secret (base64). Pending enrolment until totp_enabled_at is set.
    totp_secret: Mapped[Optional[str]] = mapped_column(String(512))
    totp_enabled_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    totp_last_step: Mapped[Optional[int]] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = created_at_column()
    last_login_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    roles: Mapped[List["UserRole"]] = relationship(
        back_populates="user",
        primaryjoin="and_(User.id == UserRole.user_id, UserRole.revoked_at.is_(None))",
        viewonly=True,
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name_he: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120))
    name_en: Mapped[str] = mapped_column(String(120))
    is_business_role: Mapped[bool] = mapped_column(Boolean, default=False)


class Permission(Base):
    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(Text, default="")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_key: Mapped[str] = mapped_column(ForeignKey("permissions.key", ondelete="CASCADE"), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        Index(
            "uq_user_roles_active",
            "user_id",
            "role_id",
            "organization_id",
            unique=True,
            sqlite_where=text("revoked_at IS NULL"),
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = created_at_column()
    reason: Mapped[str] = mapped_column(Text, default="")
    revoked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship(foreign_keys=[user_id], back_populates="roles")
    role: Mapped[Role] = relationship()


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    amr: Mapped[list] = mapped_column(JSONType, default=list)
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(300))
    created_at: Mapped[datetime] = created_at_column()
    last_seen_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship()

