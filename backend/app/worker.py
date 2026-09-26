"""Background worker: e-mail delivery with retries, and deadline detection.

    python -m app.worker

With REDIS_URL set, the API pushes a wake-up after committing notifications
and the worker delivers immediately; otherwise it polls every POLL_SECONDS.
"""
from __future__ import annotations

import logging
import signal
import time

from sqlalchemy import select

from app import db as db_module
from app.config import get_settings
from app.core import clock
from app.models import Process
from app.services import audit, notifications
from app.services.audit import Actor

log = logging.getLogger("worker")
POLL_SECONDS = 15
_running = True


def record_deadlines(db) -> int:
    due = db.execute(select(Process).where(
        Process.status == "PUBLISHED", Process.submission_deadline <= clock.now(),
        Process.deadline_recorded_at.is_(None))).scalars().all()
    for process in due:
        process.deadline_recorded_at = clock.now()
        audit.record(db, "DEADLINE_REACHED", Actor.system(), process_id=process.id,
                     metadata={"deadline": process.submission_deadline})
    db.commit()
    return len(due)


def run_once() -> dict:
    with db_module.SessionLocal() as db:
        deadlines = record_deadlines(db)
        stats = notifications.deliver_pending(db)
    return {"deadlines": deadlines, **stats}


def _wait(redis_client) -> None:
    if redis_client is None:
        time.sleep(POLL_SECONDS)
        return
    try:
        redis_client.brpop("bdp:notifications:wake", timeout=POLL_SECONDS)
    except Exception:  # pragma: no cover
        time.sleep(POLL_SECONDS)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    def stop(*_):
        global _running
        _running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    redis_client = None
    if get_settings().redis_url:
        import redis

        redis_client = redis.Redis.from_url(get_settings().redis_url)
    log.info("worker started (redis=%s)", bool(redis_client))
    while _running:
        try:
            result = run_once()
            if any(result.values()):
                log.info("cycle %s", result)
        except Exception:
            log.exception("worker cycle failed")
        _wait(redis_client)


if __name__ == "__main__":
    main()
