"""Operational commands.

    python -m app.cli migrate          alembic upgrade head
    python -m app.cli seed             baseline data (roles, organization, process types, categories)
    python -m app.cli seed-demo        demonstration data (refused in production)
    python -m app.cli dev-setup        migrate + seed + seed-demo
    python -m app.cli create-admin --email E --name N [--password P]   (or BDP_ADMIN_PASSWORD)
    python -m app.cli deliver          deliver pending notifications once
    python -m app.cli audit-verify     verify the audit hash chain
    python -m app.cli audit-anchor     print the current audit head (for external anchoring)
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app import db as db_module
from app.config import get_settings


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    command.upgrade(cfg, "head")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    sub.add_parser("seed")
    sub.add_parser("seed-demo")
    sub.add_parser("dev-setup")
    admin_p = sub.add_parser("create-admin")
    admin_p.add_argument("--email", required=True)
    admin_p.add_argument("--name", required=True)
    # Prefer the environment variable: a --password argument shows in `ps`.
    admin_p.add_argument("--password", default=None)
    sub.add_parser("deliver")
    sub.add_parser("audit-verify")
    sub.add_parser("audit-anchor")
    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command in ("migrate", "dev-setup"):
        _migrate()
        print("migrations applied")
    if args.command in ("seed", "dev-setup"):
        from app.seed.baseline import seed_baseline

        with db_module.SessionLocal() as db:
            seed_baseline(db)
        print("baseline seeded")
    if args.command in ("seed-demo", "dev-setup"):
        if settings.is_production:
            print("refusing to seed demo data in production", file=sys.stderr)
            return 2
        from app.seed.demo import seed_demo

        with db_module.SessionLocal() as db:
            result = seed_demo(db)
        print("demo data:", "already present" if result.get("skipped") else result)
    if args.command == "create-admin":
        from app.core.security import hash_password
        from app.models import User
        from app.services import audit
        from app.services.audit import Actor
        from app.services.suppliers import default_organization, grant_role

        import os

        args.password = args.password or os.environ.get("BDP_ADMIN_PASSWORD", "")
        if len(args.password) < 12:
            print("password must be at least 12 characters", file=sys.stderr)
            return 2
        with db_module.SessionLocal() as db:
            email = args.email.strip().lower()
            if db.execute(select(User.id).where(User.email == email)).first():
                print("user already exists", file=sys.stderr)
                return 2
            org = default_organization(db)
            user = User(id=uuid.uuid4(), organization_id=org.id, email=email, full_name=args.name, kind="staff",
                        password_hash=hash_password(args.password), locale="he")
            db.add(user)
            db.flush()
            grant_role(db, user, "system_admin", org.id, None, "created from CLI")
            audit.record(db, "USER_CREATED", Actor(None, "cli", None),
                         metadata={"user_id": user.id, "role": "system_admin", "via": "cli"})
            db.commit()
        print(f"administrator {email} created")
    if args.command == "deliver":
        from app.services.notifications import deliver_pending

        with db_module.SessionLocal() as db:
            print(deliver_pending(db, limit=1000))
    if args.command in ("audit-verify", "audit-anchor"):
        from app.services.audit import verify_audit_chain

        with db_module.SessionLocal() as db:
            report = verify_audit_chain(db)
        if args.command == "audit-anchor":
            print(f"{report.checked} {report.head_hash}")
        else:
            print(f"valid={report.valid} checked={report.checked} "
                  f"first_broken={report.first_broken_sequence} reason={report.reason} head={report.head_hash}")
            return 0 if report.valid else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
