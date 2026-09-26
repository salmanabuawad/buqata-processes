from __future__ import annotations

from typing import Any, Dict, Optional


class DomainError(Exception):
    """A business-rule failure with a stable, translatable code."""

    status_code = 400

    def __init__(self, code: str, message: str = "", details: Optional[Dict[str, Any]] = None,
                 status_code: Optional[int] = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code


class NotAuthenticated(DomainError):
    status_code = 401

    def __init__(self, message: str = "Sign in required"):
        super().__init__("not_authenticated", message)


class Forbidden(DomainError):
    status_code = 403

    def __init__(self, code: str = "forbidden", message: str = "Not permitted", details=None):
        super().__init__(code, message, details)


class NotFound(DomainError):
    status_code = 404

    def __init__(self, what: str = "resource"):
        super().__init__("not_found", f"{what} not found")


class Conflict(DomainError):
    status_code = 409


class Invalid(DomainError):
    status_code = 422
