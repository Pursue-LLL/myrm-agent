"""Schema of the skill-evolution database and the upgrades of an existing one to the current schema and vocabulary.

[INPUT]
- (none)

[OUTPUT]
- SCHEMA_DDL: Idempotent CREATE statements for the skills, rejections and constraints tables.
- migrate_existing_db: Bring a database written by an earlier version up to date.

[POS]
Schema and data migrations run by SkillStore on every open; each step is idempotent.
"""

from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

__all__ = ["SCHEMA_DDL", "migrate_existing_db"]

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS skills (
    skill_id            TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    content             TEXT NOT NULL,
    path                TEXT NOT NULL DEFAULT '',

    evolution_type      TEXT NOT NULL,
    version             INTEGER NOT NULL DEFAULT 1,
    parent_id           TEXT,
    change_summary      TEXT NOT NULL DEFAULT '',
    lineage_created_at  TEXT NOT NULL,
    lineage_created_by  TEXT NOT NULL DEFAULT '',

    verification_steps  TEXT NOT NULL DEFAULT '[]',
    eval_cases          TEXT NOT NULL DEFAULT '[]',
    environment         TEXT,

    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    is_active           INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
CREATE INDEX IF NOT EXISTS idx_skills_parent ON skills(parent_id);
CREATE INDEX IF NOT EXISTS idx_skills_version ON skills(skill_id, version);
CREATE INDEX IF NOT EXISTS idx_skills_active ON skills(is_active);
CREATE INDEX IF NOT EXISTS idx_skills_updated ON skills(updated_at);

CREATE TABLE IF NOT EXISTS evolution_rejections (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id            TEXT NOT NULL,
    trigger_type        TEXT NOT NULL,
    proposed_type       TEXT NOT NULL,
    rejection_reason    TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 0.5,
    trigger_context     TEXT NOT NULL DEFAULT '',
    rejected_at         TEXT NOT NULL,
    FOREIGN KEY(skill_id) REFERENCES skills(skill_id)
);

CREATE INDEX IF NOT EXISTS idx_rejections_skill ON evolution_rejections(skill_id);
CREATE INDEX IF NOT EXISTS idx_rejections_trigger ON evolution_rejections(trigger_type);
CREATE INDEX IF NOT EXISTS idx_rejections_time ON evolution_rejections(rejected_at);

CREATE TABLE IF NOT EXISTS evolution_constraints (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id            TEXT NOT NULL,
    constraint_text     TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    FOREIGN KEY(skill_id) REFERENCES skills(skill_id)
);

CREATE INDEX IF NOT EXISTS idx_constraints_skill ON evolution_constraints(skill_id);
CREATE INDEX IF NOT EXISTS idx_constraints_time ON evolution_constraints(created_at);
"""


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
