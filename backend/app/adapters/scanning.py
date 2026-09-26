"""Upload inspection: magic-byte checks and a malware-scanner hook."""
from __future__ import annotations

from typing import Protocol

# Leading bytes for the formats we accept. Office Open XML and zip share PK\x03\x04.
_MAGIC = {
    ".pdf": [b"%PDF-"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".zip": [b"PK\x03\x04", b"PK\x05\x06"],
    ".docx": [b"PK\x03\x04"],
    ".xlsx": [b"PK\x03\x04"],
    ".doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    ".xls": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
}

MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".zip": "application/zip",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
}


def magic_matches(extension: str, data: bytes) -> bool:
    signatures = _MAGIC.get(extension)
    if signatures is None:
        return False
    return any(data.startswith(sig) for sig in signatures)


class MalwareScanner(Protocol):
    name: str

    def scan(self, data: bytes) -> tuple[bool, str]:
        """Return (clean, detail)."""


class NoopScanner:
    """Development scanner. Production wires ClamAV (clamd INSTREAM) or a
    cloud scanning service behind the same protocol."""

    name = "noop"

    def scan(self, data: bytes) -> tuple[bool, str]:
        # The EICAR test string is still refused so the rejection path is exercised.
        if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data:
            return False, "EICAR test signature"
        return True, "not scanned (development scanner)"


_scanner: MalwareScanner = NoopScanner()


def get_scanner() -> MalwareScanner:
    return _scanner
