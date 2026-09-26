"""SecureVaultService — envelope encryption for sealed submissions.

    payload / files ──AES-256-GCM(DEK)──▶ ciphertext
    DEK ──RSA-OAEP(vault public key)──▶ wrapped_dek
    vault private key ──KMS.wrap──▶ wrapped_private_key

Sealing needs only the public key. The private key is unwrapped exclusively by
`open_vault` (called by the opening workflow after the policy passes) and by
content reads on a vault that is already OPENED. There is no per-submission
open: a vault is sealed or opened as a whole.
"""
from __future__ import annotations

import json
import os
import secrets
import uuid
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.orm import Session

from app.adapters.kms import get_kms
from app.adapters.storage import get_storage, new_storage_key
from app.core import clock
from app.core.errors import Forbidden
from app.core.security import sha256_hex
from app.models import Process, StoredFile, Submission, SubmissionDocument, SubmissionVersion, Vault
from app.services import audit
from app.services.audit import Actor

_OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
RSA_BITS = 3072


class VaultSealed(Forbidden):
    def __init__(self):
        super().__init__("vault_sealed", "Submissions are sealed until the vault is opened")


class IntegrityFailure(Exception):
    def __init__(self, stored_file_id: uuid.UUID, reason: str):
        super().__init__(reason)
        self.stored_file_id = stored_file_id
        self.reason = reason


@dataclass
class IncomingFile:
    kind: str
    filename: str
    mime_type: str
    data: bytes


@dataclass
class SealResult:
    version: SubmissionVersion
    payload_hash: str
    receipt_hash: str
    files: List[Tuple[str, str, int, str]]  # (kind, filename, size, sha256)


def _context(vault: Vault) -> str:
    return f"bdp-vault:{vault.id}:process:{vault.process_id}"


def create_vault(db: Session, process: Process) -> Vault:
    kms = get_kms()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=RSA_BITS)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    private_der = private_key.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    vault = Vault(id=uuid.uuid4(), process_id=process.id, status="SEALED",
                  kms_provider=kms.provider, kms_key_ref=kms.key_ref, public_key_pem=public_pem,
                  wrapped_private_key=b"")
    vault.wrapped_private_key = kms.wrap(private_der, _context(vault))
    del private_key, private_der
    db.add(vault)
    db.flush()
    return vault


def _unwrap_private_key(vault: Vault) -> rsa.RSAPrivateKey:
    der = get_kms().unwrap(vault.wrapped_private_key, _context(vault))
    return serialization.load_der_private_key(der, password=None)


def seal_submission(
    db: Session,
    vault: Vault,
    submission: Submission,
    payload: dict,
    files: Sequence[IncomingFile],
    submitted_by: uuid.UUID,
    version_no: int,
) -> SealResult:
    if vault.status != "SEALED":
        raise Forbidden("vault_not_sealed", "This vault no longer accepts submissions")
    public_key = serialization.load_pem_public_key(vault.public_key_pem.encode())
    dek = AESGCM.generate_key(bit_length=256)
    aead = AESGCM(dek)
    version_id = uuid.uuid4()

    salted = json.dumps({"salt": secrets.token_hex(16), "data": payload}, sort_keys=True,
                        separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload_hash = sha256_hex(salted)
    payload_nonce = os.urandom(12)
    version = SubmissionVersion(
        id=version_id,
        submission_id=submission.id,
        version_no=version_no,
        submitted_by=submitted_by,
        submitted_at=clock.now(),
        wrapped_dek=public_key.encrypt(dek, _OAEP),
        payload_nonce=payload_nonce,
        payload_ciphertext=aead.encrypt(payload_nonce, salted, f"{version_id}:payload".encode()),
        payload_hash=payload_hash,
        receipt_hash="",
        is_current=True,
    )
    storage = get_storage()
    file_rows: List[Tuple[str, str, int, str]] = []
    for incoming in files:
        stored_id = uuid.uuid4()
        nonce = os.urandom(12)
        digest = sha256_hex(incoming.data)
        key = new_storage_key("sealed")
        storage.put(key, aead.encrypt(nonce, incoming.data, f"{version_id}:file:{stored_id}".encode()))
        stored = StoredFile(
            id=stored_id, storage_key=key, original_filename=incoming.filename, mime_type=incoming.mime_type,
            size_bytes=len(incoming.data), sha256=digest, encrypted=True, integrity_status="UNVERIFIED",
            uploaded_by=submitted_by, uploaded_at=clock.now(),
        )
        db.add(stored)
        version.documents.append(SubmissionDocument(stored_file_id=stored_id, kind=incoming.kind, nonce=nonce))
        file_rows.append((incoming.kind, incoming.filename, len(incoming.data), digest))
    receipt_material = json.dumps(
        {"submission": str(submission.id), "version": version_no, "payload": payload_hash,
         "files": sorted(f[3] for f in file_rows), "at": version.submitted_at.isoformat()},
        sort_keys=True,
    )
    version.receipt_hash = sha256_hex(receipt_material.encode())
    del dek, aead
    db.add(version)
    db.flush()
    return SealResult(version, payload_hash, version.receipt_hash, file_rows)


def _require_opened(vault: Vault, actor: Actor, submission_id: Optional[uuid.UUID] = None) -> None:
    if vault.status != "OPENED":
        audit.record_independent("SEALED_ACCESS_DENIED", actor, process_id=vault.process_id,
                                 submission_id=submission_id)
        raise VaultSealed()


def _decrypt_dek(private_key: rsa.RSAPrivateKey, version: SubmissionVersion) -> AESGCM:
    return AESGCM(private_key.decrypt(version.wrapped_dek, _OAEP))


def _decrypt_payload(aead: AESGCM, version: SubmissionVersion) -> dict:
    plain = aead.decrypt(version.payload_nonce, version.payload_ciphertext, f"{version.id}:payload".encode())
    if sha256_hex(plain) != version.payload_hash:
        raise IntegrityFailure(version.id, "payload_hash_mismatch")
    return json.loads(plain)["data"]


def _decrypt_document(aead: AESGCM, version: SubmissionVersion, document: SubmissionDocument) -> bytes:
    stored = document.file
    try:
        ciphertext = get_storage().get(stored.storage_key)
        plain = aead.decrypt(document.nonce, ciphertext, f"{version.id}:file:{stored.id}".encode())
    except (InvalidTag, FileNotFoundError, OSError) as exc:
        raise IntegrityFailure(stored.id, f"decrypt_failed:{type(exc).__name__}") from exc
    if sha256_hex(plain) != stored.sha256:
        raise IntegrityFailure(stored.id, "sha256_mismatch")
    return plain


@dataclass
class OpenReport:
    opened_submissions: int
    verified_files: int
    failed_files: List[dict]
    alert_event_ids: List[uuid.UUID]


def open_vault(db: Session, vault: Vault, submissions: Sequence[Submission], actor: Actor,
               opening_request_id: uuid.UUID) -> OpenReport:
    """Open every current submission in one step and verify every file.
    Called only by the opening service after the full policy has passed."""
    if vault.status == "OPENED":
        raise Forbidden("vault_already_open", "Vault already opened")
    private_key = _unwrap_private_key(vault)
    opened_at = clock.now()
    verified, failed, alerts = 0, [], []
    for submission in submissions:
        version = submission.current_version
        if version is None:
            continue
        aead = _decrypt_dek(private_key, version)
        try:
            _decrypt_payload(aead, version)
        except (InvalidTag, IntegrityFailure):
            failed.append({"submission_id": str(submission.id), "part": "payload"})
            alerts.append(audit.record(db, "FILE_INTEGRITY_FAILURE", actor, process_id=vault.process_id,
                                       submission_id=submission.id, metadata={"part": "payload"}).id)
        for document in version.documents:
            try:
                _decrypt_document(aead, version, document)
            except IntegrityFailure as failure:
                document.file.integrity_status = "FAILED"
                failed.append({"submission_id": str(submission.id), "stored_file_id": str(failure.stored_file_id),
                               "reason": failure.reason})
                alerts.append(audit.record(
                    db, "FILE_INTEGRITY_FAILURE", actor, process_id=vault.process_id, submission_id=submission.id,
                    metadata={"stored_file_id": failure.stored_file_id, "reason": failure.reason}).id)
            else:
                document.file.integrity_status = "OK"
                verified += 1
        submission.status = "OPENED"
        submission.opened_at = opened_at
    del private_key
    vault.status = "OPENED"
    vault.opened_at = opened_at
    vault.opening_request_id = opening_request_id
    db.flush()
    return OpenReport(sum(1 for s in submissions if s.current_version is not None), verified, failed, alerts)


def read_payloads(vault: Vault, submissions: Sequence[Submission], actor: Actor) -> dict:
    """Decrypt current payloads for an OPENED vault. Returns {submission_id: payload or None}."""
    _require_opened(vault, actor)
    private_key = _unwrap_private_key(vault)
    result = {}
    for submission in submissions:
        version = submission.current_version
        if version is None:
            continue
        try:
            result[submission.id] = _decrypt_payload(_decrypt_dek(private_key, version), version)
        except (InvalidTag, IntegrityFailure):
            result[submission.id] = None
    del private_key
    return result


def read_document(db: Session, vault: Vault, submission: Submission, document: SubmissionDocument,
                  actor: Actor) -> bytes:
    _require_opened(vault, actor, submission.id)
    version = document.version
    if submission.current_version_id != version.id:
        raise Forbidden("superseded_version", "Only the final submitted version is opened")
    private_key = _unwrap_private_key(vault)
    try:
        return _decrypt_document(_decrypt_dek(private_key, version), version, document)
    except IntegrityFailure as failure:
        document.file.integrity_status = "FAILED"
        db.commit()
        audit.record_independent("FILE_INTEGRITY_FAILURE", actor, process_id=vault.process_id,
                                 submission_id=submission.id,
                                 metadata={"stored_file_id": failure.stored_file_id, "reason": failure.reason})
        raise Forbidden("file_integrity_failure", "The file failed integrity verification and is blocked") from failure
    finally:
        del private_key
