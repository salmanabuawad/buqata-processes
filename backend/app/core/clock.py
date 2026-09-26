"""The one source of business time. Tests freeze it with `frozen_at`."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

_frozen: Optional[datetime] = None


def now() -> datetime:
    return _frozen if _frozen is not None else datetime.now(timezone.utc)


def set_now(value: Optional[datetime]) -> None:
    global _frozen
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    _frozen = value


@contextmanager
def frozen_at(value: datetime) -> Iterator[None]:
    previous = _frozen
    set_now(value)
    try:
        yield
    finally:
        set_now(previous)


def ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
