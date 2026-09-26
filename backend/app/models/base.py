from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.db import UTCDateTime


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=new_id)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(UTCDateTime, default=clock.now, nullable=False)
