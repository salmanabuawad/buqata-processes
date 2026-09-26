"""Database-level guards installed by the migration (and by the test fixture).

The audit table rejects UPDATE and DELETE. A superuser can drop the trigger —
that is precisely the case the hash chain exists to expose.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

POSTGRES = [
    """
    CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'audit_events is append-only';
    END;
    $$ LANGUAGE plpgsql;
    """,
    "DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events",
    """
    CREATE TRIGGER audit_events_no_update BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()
    """,
]

SQLITE = [
    "DROP TRIGGER IF EXISTS audit_events_no_update",
    "DROP TRIGGER IF EXISTS audit_events_no_delete",
    """
    CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events
    BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END
    """,
    """
    CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events
    BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END
    """,
]


def install(connection: Connection) -> None:
    statements = POSTGRES if connection.dialect.name == "postgresql" else SQLITE
    for statement in statements:
        connection.execute(text(statement))


def uninstall(connection: Connection) -> None:
    if connection.dialect.name == "postgresql":
        connection.execute(text("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events"))
        connection.execute(text("DROP FUNCTION IF EXISTS audit_events_append_only()"))
    else:
        connection.execute(text("DROP TRIGGER IF EXISTS audit_events_no_update"))
        connection.execute(text("DROP TRIGGER IF EXISTS audit_events_no_delete"))
