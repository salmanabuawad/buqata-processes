"""Local TOTP two-step verification: KMS-wrapped secret, enabled time, replay guard

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

import app.db

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("totp_secret", existing_type=sa.String(length=64), type_=sa.String(length=512),
                           existing_nullable=True)
        batch.add_column(sa.Column("totp_enabled_at", app.db.UTCDateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("totp_last_step", sa.BigInteger(), nullable=True))
    # No secret was ever written before this revision; clear any stray value so
    # nothing unwrapped can be mistaken for an enrolled authenticator.
    op.execute("UPDATE users SET totp_secret = NULL")


def downgrade() -> None:
    op.execute("UPDATE users SET totp_secret = NULL")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("totp_last_step")
        batch.drop_column("totp_enabled_at")
        batch.alter_column("totp_secret", existing_type=sa.String(length=512), type_=sa.String(length=64),
                           existing_nullable=True)
