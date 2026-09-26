"""Quotation-request flexibility: manual distribution changes, opening modes

Revision ID: 0002
Revises: 0001
"""
import json

import sqlalchemy as sa
from alembic import op

import app.db

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("distribution_recipients") as batch:
        batch.add_column(sa.Column("removed_at", app.db.UTCDateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("removed_by", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("removal_reason", sa.Text(), nullable=True))
        batch.create_foreign_key("fk_recipient_removed_by", "users", ["removed_by"], ["id"])

    # Quotation requests created before opening modes existed were sealed until
    # the deadline; keep exactly that behaviour for them.
    bind = op.get_bind()
    param = "CAST(:v AS jsonb)" if bind.dialect.name == "postgresql" else ":v"
    rows = bind.execute(sa.text("SELECT id, details FROM processes WHERE process_type = 'rfq'")).fetchall()
    for pid, details in rows:
        data = details if isinstance(details, dict) else json.loads(details or "{}")
        if "opening_mode" in data:
            continue
        data["opening_mode"] = "sealed_after_deadline"
        bind.execute(sa.text(f"UPDATE processes SET details = {param} WHERE id = :i"),
                     {"v": json.dumps(data, ensure_ascii=False), "i": pid})
        policy = bind.execute(sa.text("SELECT id, rules FROM opening_policies WHERE process_id = :i"), {"i": pid}).first()
        if policy is not None:
            rules = policy[1] if isinstance(policy[1], list) else json.loads(policy[1] or "[]")
            if not any(r.get("type") == "time" for r in rules):
                rules.insert(0, {"type": "time"})
                bind.execute(sa.text(f"UPDATE opening_policies SET rules = {param} WHERE id = :i"),
                             {"v": json.dumps(rules), "i": policy[0]})


def downgrade() -> None:
    with op.batch_alter_table("distribution_recipients") as batch:
        batch.drop_constraint("fk_recipient_removed_by", type_="foreignkey")
        batch.drop_column("removal_reason")
        batch.drop_column("removed_by")
        batch.drop_column("removed_at")
