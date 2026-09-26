"""Key management behind a protocol.

Production deployments implement `KeyManagementService` against AWS KMS
(Encrypt/Decrypt with EncryptionContext), Azure Key Vault (wrapKey/unwrapKey)
or a PKCS#11 HSM. `LocalKms` exists for development and demonstrations and
refuses to run when ENVIRONMENT=production.
"""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings


class KeyManagementService(Protocol):
    provider: str
    key_ref: str

    def wrap(self, plaintext: bytes, context: str) -> bytes: ...
    def unwrap(self, ciphertext: bytes, context: str) -> bytes: ...


class LocalKms:
    provider = "local"

    def __init__(self, master_key: bytes, key_ref: str = "local-dev-master"):
        if len(master_key) != 32:
            raise ValueError("Local KMS master key must be 32 bytes")
        self._aead = AESGCM(master_key)
        self.key_ref = key_ref

    def wrap(self, plaintext: bytes, context: str) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._aead.encrypt(nonce, plaintext, context.encode("utf-8"))

    def unwrap(self, ciphertext: bytes, context: str) -> bytes:
        return self._aead.decrypt(ciphertext[:12], ciphertext[12:], context.encode("utf-8"))


def _load_local_master_key() -> bytes:
    settings = get_settings()
    if settings.vault_master_key:
        return base64.b64decode(settings.vault_master_key)
    path = Path(settings.vault_master_key_file)
    if path.exists():
        return base64.b64decode(path.read_text().strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    path.write_text(base64.b64encode(key).decode())
    return key


_kms: KeyManagementService | None = None


def get_kms() -> KeyManagementService:
    global _kms
    if _kms is None:
        settings = get_settings()
        if settings.kms_provider != "local":
            raise RuntimeError(f"KMS provider {settings.kms_provider!r} is not configured in this build")
        if settings.is_production:
            raise RuntimeError(
                "LocalKms is for development and demonstration environments only. Production "
                "needs a managed KMS or HSM adapter — see docs/SECURITY_MODEL.md §4."
            )
        _kms = LocalKms(_load_local_master_key())
    return _kms


def set_kms(kms: KeyManagementService | None) -> None:
    global _kms
    _kms = kms
