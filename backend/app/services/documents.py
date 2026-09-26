"""DocumentService — upload validation, hashing and plain (non-sealed) storage.

Sealed submission files go through the vault instead; they share the same
validation here.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.adapters.scanning import MIME_BY_EXTENSION, get_scanner, magic_matches
from app.adapters.storage import get_storage, new_storage_key
from app.config import get_settings
from app.core import clock
from app.core.errors import Forbidden, Invalid
from app.core.security import sha256_hex
from app.models import StoredFile
from app.services import audit
from app.services.audit import Actor

MAX_FILENAME = 200


@dataclass
class ValidatedUpload:
    filename: str
    extension: str
    mime_type: str
    data: bytes


def _clean_filename(name: str) -> str:
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')
    return (name or "file")[:MAX_FILENAME]


def validate_upload(filename: str, data: bytes, allowed_extensions: Optional[Iterable[str]] = None) -> ValidatedUpload:
    settings = get_settings()
    clean = _clean_filename(filename)
    extension = os.path.splitext(clean)[1].lower()
    allowed = set(settings.allowed_upload_extensions)
    if allowed_extensions is not None:
        allowed &= set(allowed_extensions)
    if extension not in allowed:
        raise Invalid("file_type_not_allowed", f"{extension or 'no extension'} is not an allowed file type",
                      {"filename": clean, "allowed": sorted(allowed)})
    if not data:
        raise Invalid("file_empty", "The file is empty", {"filename": clean})
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise Invalid("file_too_large", f"Files are limited to {settings.max_upload_mb} MB", {"filename": clean})
    if not magic_matches(extension, data):
        raise Invalid("file_content_mismatch", "The file content does not match its type", {"filename": clean})
    clean_ok, detail = get_scanner().scan(data)
    if not clean_ok:
        raise Invalid("file_rejected_by_scanner", "The file was rejected by the malware scanner",
                      {"filename": clean, "detail": detail})
    return ValidatedUpload(clean, extension, MIME_BY_EXTENSION.get(extension, "application/octet-stream"), data)


def store_plain(db: Session, upload: ValidatedUpload, actor: Actor, *, prefix: str,
                process_id: Optional[uuid.UUID] = None) -> StoredFile:
    key = new_storage_key(prefix)
    get_storage().put(key, upload.data)
    stored = StoredFile(
        id=uuid.uuid4(), storage_key=key, original_filename=upload.filename, mime_type=upload.mime_type,
        size_bytes=len(upload.data), sha256=sha256_hex(upload.data), encrypted=False, integrity_status="OK",
        uploaded_by=actor.user_id, uploaded_at=clock.now(),
    )
    db.add(stored)
    db.flush()
    audit.record(db, "FILE_UPLOADED", actor, process_id=process_id,
                 metadata={"stored_file_id": stored.id, "sha256": stored.sha256, "size": stored.size_bytes,
                           "mime": stored.mime_type})
    return stored


def read_plain(db: Session, stored: StoredFile, actor: Actor, process_id: Optional[uuid.UUID] = None) -> bytes:
    try:
        data = get_storage().get(stored.storage_key)
    except (FileNotFoundError, OSError):
        data = None
    if data is None or sha256_hex(data) != stored.sha256:
        stored.integrity_status = "FAILED"
        db.commit()
        audit.record_independent("FILE_INTEGRITY_FAILURE", actor, process_id=process_id,
                                 metadata={"stored_file_id": stored.id, "reason": "sha256_mismatch"})
        raise Forbidden("file_integrity_failure", "The file failed integrity verification and is blocked")
    return data
