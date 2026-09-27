"""RFC 6238 time-based one-time passwords (HMAC-SHA1, 6 digits, 30 s). Standard library only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from typing import Optional
from urllib.parse import quote, urlencode

STEP_SECONDS = 30
DIGITS = 6
SECRET_BYTES = 20
# Accept the previous and next step as well, for clock drift on the user's phone.
DRIFT_STEPS = 1


def new_secret() -> bytes:
    return secrets.token_bytes(SECRET_BYTES)


def to_base32(secret: bytes) -> str:
    return base64.b32encode(secret).decode("ascii").rstrip("=")


def time_step(unix_seconds: float) -> int:
    return int(unix_seconds // STEP_SECONDS)


def code_at(secret: bytes, step: int) -> str:
    digest = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def matching_step(secret: bytes, code: str, unix_seconds: float, after_step: Optional[int] = None) -> Optional[int]:
    """The time step `code` belongs to, or None. Steps at or before `after_step` are refused (replay)."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    current = time_step(unix_seconds)
    found = None
    for step in range(current - DRIFT_STEPS, current + DRIFT_STEPS + 1):
        # Compare every candidate so timing does not reveal which window matched.
        if hmac.compare_digest(code_at(secret, step), code) and found is None:
            found = step
    if found is None or (after_step is not None and found <= after_step):
        return None
    return found


def provisioning_uri(secret: bytes, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    query = urlencode({"secret": to_base32(secret), "issuer": issuer, "algorithm": "SHA1",
                       "digits": DIGITS, "period": STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"
