"""Upgrades of an existing skill-evolution database to the current schema and vocabulary.

[INPUT]
- (none)

[OUTPUT]
- migrate_existing_db: Bring a database written by an earlier version up to date.

[POS]
Schema and data migrations run by SkillStore on every open; each step is idempotent.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

__all__ = ["migrate_existing_db"]

# Notes the engine and the screener once saved on their own as constraints; the table keeps only what a user rejected.
_AUTOMATIC_CONSTRAINT_PREFIXES = ("FIX succeeded", "DERIVED succeeded", "LLM screener rejected FIX")


def migrate_existing_db(conn: sqlite3.Connection) -> None:
    """Apply every migration; the caller holds the write lock and commits."""
    _add_record_columns(conn)
    _purge_automatic_constraints(conn)
    _retire_description_evolution_type(conn)


def _add_record_columns(conn: sqlite3.Connection) -> None:
    """Add verification_steps/eval_cases/evolution_locked/environment columns for existing DBs."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(skills)").fetchall()}
    if "verification_steps" not in cols:
        conn.execute("ALTER TABLE skills ADD COLUMN verification_steps TEXT NOT NULL DEFAULT '[]'")
    if "eval_cases" not in cols:
        conn.execute("ALTER TABLE skills ADD COLUMN eval_cases TEXT NOT NULL DEFAULT '[]'")
    if "evolution_locked" not in cols:
        conn.execute("ALTER TABLE skills ADD COLUMN evolution_locked INTEGER NOT NULL DEFAULT 0")
    if "environment" not in cols:
        conn.execute("ALTER TABLE skills ADD COLUMN environment TEXT")


def _purge_automatic_constraints(conn: sqlite3.Connection) -> None:
    """Drop the constraints nobody rejected: the exact, case-sensitive prefixes the engine and the screener wrote."""
    removed = sum(
        conn.execute(
            "DELETE FROM evolution_constraints WHERE substr(constraint_text, 1, ?) = ?", (len(prefix), prefix)
        ).rowcount
        for prefix in _AUTOMATIC_CONSTRAINT_PREFIXES
    )
    if removed:
        logger.info("Removed %d automatic evolution constraints; the table keeps user rejection reasons only", removed)


def _retire_description_evolution_type(conn: sqlite3.Connection) -> None:
    """Load the records of the retired description-only evolution as FIX, the nearest type left."""
    updated = conn.execute(
        "UPDATE skills SET evolution_type = 'fix' WHERE evolution_type = 'optimize_description'"
    ).rowcount
    if updated:
        logger.warning("Re-typed %d skill record(s) of the retired description-only evolution as FIX", updated)
