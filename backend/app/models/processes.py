from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, JSONType, UTCDateTime
from app.models.base import created_at_column, uuid_pk
from app.models.suppliers import Category, StoredFile, Supplier


class ProcessType(Base):
    __tablename__ = "process_types"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name_he: Mapped[str] = mapped_column(String(120))
    name_ar: Mapped[str] = mapped_column(String(120))
    name_en: Mapped[str] = mapped_column(String(120))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    default_config: Mapped[dict] = mapped_column(JSONType, default=dict)


class Process(Base):
    __tablename__ = "processes"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    process_type: Mapped[str] = mapped_column(ForeignKey("process_types.key"), index=True)
    reference_number: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    submission_deadline: Mapped[datetime] = mapped_column(UTCDateTime)
    opening_time: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    published_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    deadline_recorded_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    closed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    cancelled_reason: Mapped[Optional[str]] = mapped_column(Text)
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_email: Mapped[str] = mapped_column(String(254), default="")
    contact_phone: Mapped[str] = mapped_column(String(40), default="")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = created_at_column()
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("process_versions.id", use_alter=True, name="fk_process_current_version")
    )

    categories: Mapped[List["ProcessCategory"]] = relationship(cascade="all, delete-orphan")
    documents: Mapped[List["ProcessDocument"]] = relationship(cascade="all, delete-orphan")
    participants: Mapped[List["ProcessParticipant"]] = relationship(
        primaryjoin="and_(Process.id == ProcessParticipant.process_id, ProcessParticipant.revoked_at.is_(None))",
        viewonly=True,
    )

    @property
    def opening_at(self) -> datetime:
        return self.opening_time or self.submission_deadline


class ProcessVersion(Base):
    __tablename__ = "process_versions"
    __table_args__ = (UniqueConstraint("process_id", "version_no"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"))
    version_no: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSONType)
    content_hash: Mapped[str] = mapped_column(String(64))
    frozen_at: Mapped[datetime] = created_at_column()
    frozen_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class ProcessCategory(Base):
    __tablename__ = "process_categories"

    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), primary_key=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), primary_key=True)

    category: Mapped[Category] = relationship()


class ProcessDocument(Base):
    __tablename__ = "process_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), index=True)
    stored_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stored_files.id"))
    kind: Mapped[str] = mapped_column(String(40), default="attachment")
    title: Mapped[str] = mapped_column(String(200))

    file: Mapped[StoredFile] = relationship()


class ProcessParticipant(Base):
    __tablename__ = "process_participants"

    id: Mapped[uuid.UUID] = uuid_pk()
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    participation: Mapped[str] = mapped_column(String(30))
    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    granted_at: Mapped[datetime] = created_at_column()
    reason: Mapped[str] = mapped_column(Text, default="")
    revoked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)


class DistributionSnapshot(Base):
    __tablename__ = "distribution_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # INITIAL | SUPPLEMENTAL
    rule: Mapped[dict] = mapped_column(JSONType)
    recipient_count: Mapped[int] = mapped_column(Integer)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_column()
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))


class DistributionRecipient(Base):
    __tablename__ = "distribution_recipients"
    __table_args__ = (UniqueConstraint("process_id", "supplier_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("distribution_snapshots.id"))
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), index=True)
    match_reason: Mapped[dict] = mapped_column(JSONType)
    invitation_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    notification_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("notifications.id"))
    notified_at: Mapped[datetime] = created_at_column()
    opened_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    submission_started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    supplier: Mapped[Supplier] = relationship()


class Vault(Base):
    __tablename__ = "vaults"

    id: Mapped[uuid.UUID] = uuid_pk()
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="SEALED")
    kms_provider: Mapped[str] = mapped_column(String(40))
    kms_key_ref: Mapped[str] = mapped_column(String(200))
    # Sealing uses only the public key; the private key exists at rest only as
    # KMS ciphertext and is unwrapped by the opening workflow.
    public_key_pem: Mapped[str] = mapped_column(Text)
    wrapped_private_key: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = created_at_column()
    opened_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    opening_request_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("opening_requests.id", use_alter=True, name="fk_vault_opening_request")
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("process_id", "supplier_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), index=True)
    supplier_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("suppliers.id"))
    applicant_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"))
    receipt_number: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="STARTED")
    started_at: Mapped[datetime] = created_at_column()
    submitted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    opened_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("submission_versions.id", use_alter=True, name="fk_submission_current_version")
    )

    supplier: Mapped[Optional[Supplier]] = relationship()
    current_version: Mapped[Optional["SubmissionVersion"]] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )


class SubmissionVersion(Base):
    __tablename__ = "submission_versions"
    __table_args__ = (UniqueConstraint("submission_id", "version_no"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = created_at_column()
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    payload_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    payload_hash: Mapped[str] = mapped_column(String(64))
    receipt_hash: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    superseded_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    documents: Mapped[List["SubmissionDocument"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class SubmissionDocument(Base):
    __tablename__ = "submission_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    submission_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submission_versions.id"), index=True)
    stored_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stored_files.id"))
    kind: Mapped[str] = mapped_column(String(40))
    nonce: Mapped[bytes] = mapped_column(LargeBinary)

    version: Mapped[SubmissionVersion] = relationship(back_populates="documents")
    file: Mapped[StoredFile] = relationship()


class OpeningPolicyRecord(Base):
    __tablename__ = "opening_policies"

    id: Mapped[uuid.UUID] = uuid_pk()
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), unique=True)
    rules: Mapped[list] = mapped_column(JSONType)
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    designated_official_ids: Mapped[list] = mapped_column(JSONType, default=list)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)


class OpeningRequest(Base):
    __tablename__ = "opening_requests"

    id: Mapped[uuid.UUID] = uuid_pk()
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), index=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = created_at_column()
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    last_evaluation: Mapped[dict] = mapped_column(JSONType, default=dict)
    executed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    approvals: Mapped[List["OpeningApproval"]] = relationship(cascade="all, delete-orphan")


class OpeningApproval(Base):
    __tablename__ = "opening_approvals"
    __table_args__ = (UniqueConstraint("opening_request_id", "approver_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    opening_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opening_requests.id"))
    approver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(10))
    decided_at: Mapped[datetime] = created_at_column()
    auth_context: Mapped[dict] = mapped_column(JSONType, default=dict)
    client_ip: Mapped[Optional[str]] = mapped_column(String(64))
    device: Mapped[dict] = mapped_column(JSONType, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = uuid_pk()
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), index=True)
    subject_submission_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("submissions.id"))
    decision_type: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = created_at_column()
    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)


class Protocol(Base):
    __tablename__ = "protocols"

    id: Mapped[uuid.UUID] = uuid_pk()
    process_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processes.id"), index=True)
    protocol_type: Mapped[str] = mapped_column(String(40))
    locale: Mapped[str] = mapped_column(String(5))
    html: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    audit_head_hash: Mapped[str] = mapped_column(String(64))
    generated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    generated_at: Mapped[datetime] = created_at_column()
