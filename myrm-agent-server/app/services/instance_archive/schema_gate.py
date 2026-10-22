"""Schema version of the running code, for gating databases that are about to go live.

[INPUT]
- app.database.migrations::MIGRATION_STATEMENTS (POS: ordered schema migrations)

[OUTPUT]
- current_schema_version: highest migration version this build can open

[POS]
A database whose applied migrations exceed this build was written by a newer
app; opening it would run against an unknown schema, so import and restore
reject it up front instead of letting the boot-time schema gate fail closed.
"""

from __future__ import annotations


def current_schema_version() -> int:
    from app.database.migrations import MIGRATION_STATEMENTS

    return len(MIGRATION_STATEMENTS) - 1
