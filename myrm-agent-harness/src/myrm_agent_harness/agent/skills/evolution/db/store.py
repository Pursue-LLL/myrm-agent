"""SQLite persistence for skill evolution system.

3-table design:
- skills: Skill records with lineage, eval_cases
- evolution_rejections: Screener rejection audit trail
- evolution_constraints: The reasons a user gave when rejecting a proposal, fed to the next proposal

Core properties:
- WAL mode for concurrent reads
- db_retry decorator for robustness
- Async-safe write path

[INPUT]
- agent.skills.evolution.core.types::SkillLineage, (POS: Data types for skill evolution system.)
- agent.skills.evolution.db._store_schema::SCHEMA_DDL, migrate_existing_db (POS: Schema and data migrations run by SkillStore on every open; each step is idempotent.)
- agent.skills.evolution.db._store_retry::db_retry (POS: Transient-error retry for SkillStore operations.)

[OUTPUT]
- SkillStore: Simplified SQLite persistence for skill evolution.

[POS]
SQLite persistence for skill evolution system.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Self

from myrm_agent_harness.agent.skills.evolution.core.types import (
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.db._store_dependencies import (
    _DEPENDENCY_TABLE_DDL,
    SkillDependencyMixin,
)
from myrm_agent_harness.agent.skills.evolution.db._store_evolution_tracking import (
    SkillEvolutionTrackingMixin,
)
from myrm_agent_harness.agent.skills.evolution.db._store_retry import db_retry
from myrm_agent_harness.agent.skills.evolution.db._store_schema import SCHEMA_DDL, migrate_existing_db
from myrm_agent_harness.agent.skills.evolution.db.store_queries import SkillStoreQueries

logger = logging.getLogger(__name__)

__all__ = ["SkillStore"]


class SkillStore(SkillEvolutionTrackingMixin, SkillDependencyMixin, SkillStoreQueries):
    """Simplified SQLite persistence for skill evolution.

    Architecture:
    - Write: async method → asyncio.to_thread → _xxx_sync → self._mu lock → self._conn
    - Read: sync method → self._reader() → temporary read-only connection (WAL parallel)
    - Complex queries: inherited from SkillStoreQueries mixin

    Lifecycle:
        store = SkillStore()
        await store.save_skill(record)
        record = store.get_skill(skill_id)
        store.close()

    Or use as async context manager:
        async with SkillStore() as store:
            await store.save_skill(record)
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize skill store.

        Args:
            db_path: Path to SQLite database file. Defaults to .myrm/skills.db
        """
        if db_path is None:
            db_dir = Path.cwd() / ".myrm"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / "skills.db"

        self._db_path = Path(db_path)
        self._mu = threading.Lock()
        self._closed = False

        # Crash recovery
        self._cleanup_wal_on_startup()

        # Persistent write connection
        self._conn = self._make_connection(read_only=False)
        self._init_db()
        logger.debug("SkillStore ready at %s", self._db_path)

    def _make_connection(self, *, read_only: bool) -> sqlite3.Connection:
        """Create optimized SQLite connection.

        Configuration:
        - WAL mode: Concurrent reads + single writer
        - 30s timeout: Handle lock contention gracefully
        - 16MB cache: Reduce disk I/O
        - Foreign keys: Ensure referential integrity
        """
        from myrm_agent_harness.utils.db.sqlite import SQLiteProfile, harden_connection_sync

        conn = sqlite3.connect(
            str(self._db_path),
            timeout=30.0,
            check_same_thread=False,  # For asyncio.to_thread()
        )
        profile = SQLiteProfile(
            busy_timeout_ms=30000,
            cache_size=-16000,  # 16 MB
            temp_store_memory=True,
            read_only=read_only,
        )
        harden_connection_sync(conn, profile, db_path=self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _reader(self) -> Iterator[sqlite3.Connection]:
        """Open temporary read-only connection for parallel reads.

        WAL mode allows concurrent readers without blocking.
        Each read gets its own connection to avoid event loop blocking.
        """
        self._ensure_open()
        conn = self._make_connection(read_only=True)
        try:
            yield conn
        finally:
            conn.close()

    def _cleanup_wal_on_startup(self) -> None:
        """Crash recovery: drop orphaned WAL/SHM companions of an empty main DB."""
        from myrm_agent_harness.utils.db.sqlite import cleanup_orphan_wal

        cleanup_orphan_wal(self._db_path)

    @db_retry()
    def _init_db(self) -> None:
        """Create tables (idempotent via IF NOT EXISTS) and run migrations."""
        with self._mu:
            self._conn.executescript(SCHEMA_DDL)
            self._conn.executescript(_DEPENDENCY_TABLE_DDL)
            migrate_existing_db(self._conn)
            self._conn.commit()

    def close(self) -> None:
        """Close persistent connection and checkpoint WAL.

        Performs WAL checkpoint to flush all data to main DB file.
        This ensures external tools see complete data.
        """
        if self._closed:
            return
        self._closed = True
        from myrm_agent_harness.utils.db.sqlite import checkpoint_truncate_sync

        checkpoint_truncate_sync(self._conn)
        with suppress(sqlite3.Error):
            self._conn.close()
        logger.debug("SkillStore closed (WAL checkpointed)")

    def __del__(self) -> None:
        """Ensure connection is closed on garbage collection."""
        with suppress(Exception):
            self.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.close()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def closed(self) -> bool:
        """Whether the store was closed and can no longer be used."""
        return self._closed

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SkillStore is closed")

    # Write operations (async)
    @db_retry()
    def _delete_skill_sync(self, skill_id: str) -> None:
        """Synchronous delete - called via asyncio.to_thread()."""
        with self._mu:
            self._conn.execute("DELETE FROM skills WHERE skill_id = ?", (skill_id,))
            self._conn.execute("DELETE FROM evolution_rejections WHERE skill_id = ?", (skill_id,))
            self._conn.execute("DELETE FROM evolution_constraints WHERE skill_id = ?", (skill_id,))
            self._delete_skill_dependencies_locked(skill_id)
            self._conn.commit()

    async def delete_skill(self, skill_id: str) -> None:
        """Delete a skill from the database.

        Args:
            skill_id: The ID of the skill to delete.
        """
        self._ensure_open()
        await asyncio.to_thread(self._delete_skill_sync, skill_id)

    async def delete_skills_by_agent(self, agent_id: str) -> int:
        """Delete all skills owned by a specific agent.

        Args:
            agent_id: The ID of the agent whose skills should be deleted.

        Returns:
            Number of skills deleted.
        """
        self._ensure_open()

        # Find all skills owned by this agent
        def _get_owned_skills() -> list[tuple[str, str]]:
            with self._reader() as conn:
                rows = conn.execute(
                    """
                    SELECT skill_id, path FROM skills
                    WHERE json_extract(environment, '$.custom_tags.scope_agent_id') = ?
                    """,
                    (agent_id,),
                ).fetchall()
                return [(row["skill_id"], row["path"]) for row in rows]

        skill_data = await asyncio.to_thread(_get_owned_skills)
        if not skill_data:
            return 0

        import os
        import shutil
        from pathlib import Path

        for sid, spath in skill_data:
            # First, delete the physical file/folder if it exists
            if spath:
                try:
                    p = Path(spath)
                    if p.exists():
                        # SKILL.md is inside a folder named after the skill, we should delete the parent folder
                        # if it's the standard layout (e.g. workspace/skill_name/SKILL.md)
                        if p.name == "SKILL.md":
                            if p.parent.name not in ["workspace", "skills", ""]:
                                shutil.rmtree(p.parent, ignore_errors=True)
                            else:
                                logger.warning("Skipping rmtree on unsafe path: %s", p.parent)
                        else:
                            os.remove(p)
                except Exception as e:
                    logger.warning("Failed to physical delete skill %s at %s: %s", sid, spath, e)

            # Then delete from database
            await self.delete_skill(sid)

        return len(skill_data)

    @db_retry()
    def _save_skill_sync(self, record: SkillRecord) -> None:
        """Synchronous save - called via asyncio.to_thread()."""
        with self._mu:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO skills (
                    skill_id, name, description, content, path,
                    evolution_type, version, parent_id, change_summary,
                    lineage_created_at, lineage_created_by,
                    verification_steps, eval_cases, environment,
                    created_at, updated_at, is_active, evolution_locked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.skill_id,
                    record.name,
                    record.description,
                    record.content,
                    record.path,
                    record.lineage.evolution_type.value,
                    record.lineage.version,
                    record.lineage.parent_id,
                    record.lineage.change_summary,
                    record.lineage.created_at.isoformat(),
                    record.lineage.created_by,
                    json.dumps(record.verification_steps, ensure_ascii=False),
                    json.dumps(record.eval_cases, ensure_ascii=False),
                    (json.dumps(record.environment.to_dict(), ensure_ascii=False) if record.environment else None),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    int(record.is_active),
                    int(record.evolution_locked),
                ),
            )
            self._sync_skill_dependencies_locked(record)
            self._conn.commit()

    @db_retry()
    def _save_skills_batch_sync(self, records: list[SkillRecord]) -> None:
        """Synchronous batch save - called via asyncio.to_thread()."""
        if not records:
            return
        with self._mu:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO skills (
                    skill_id, name, description, content, path,
                    evolution_type, version, parent_id, change_summary,
                    lineage_created_at, lineage_created_by,
                    verification_steps, eval_cases, environment,
                    created_at, updated_at, is_active, evolution_locked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        record.skill_id,
                        record.name,
                        record.description,
                        record.content,
                        record.path,
                        record.lineage.evolution_type.value,
                        record.lineage.version,
                        record.lineage.parent_id,
                        record.lineage.change_summary,
                        record.lineage.created_at.isoformat(),
                        record.lineage.created_by,
                        json.dumps(record.verification_steps, ensure_ascii=False),
                        json.dumps(record.eval_cases, ensure_ascii=False),
                        (json.dumps(record.environment.to_dict(), ensure_ascii=False) if record.environment else None),
                        record.created_at.isoformat(),
                        record.updated_at.isoformat(),
                        int(record.is_active),
                        int(record.evolution_locked),
                    )
                    for record in records
                ],
            )
            self._sync_skills_dependencies_locked(records)
            self._conn.commit()

    async def save_skills_batch(self, records: list[SkillRecord]) -> None:
        """Save or update multiple skill records in a single transaction.

        Args:
            records: List of SkillRecords to persist

        Raises:
            ValueError: If any content exceeds MAX_SKILL_CONTENT_CHARS.
        """
        for record in records:
            if record.content and len(record.content) > self.MAX_SKILL_CONTENT_CHARS:
                raise ValueError(
                    f"Skill content too large ({len(record.content)} chars, max {self.MAX_SKILL_CONTENT_CHARS}). "
                    f"Reduce the skill size before saving."
                )
        self._ensure_open()
        await asyncio.to_thread(self._save_skills_batch_sync, records)

    MAX_SKILL_CONTENT_CHARS = 65_536

    async def save_skill(self, record: SkillRecord) -> None:
        """Save or update skill record.

        Args:
            record: SkillRecord to persist

        Raises:
            ValueError: If content exceeds MAX_SKILL_CONTENT_CHARS.
        """
        if record.content and len(record.content) > self.MAX_SKILL_CONTENT_CHARS:
            raise ValueError(
                f"Skill content too large ({len(record.content)} chars, max {self.MAX_SKILL_CONTENT_CHARS}). "
                f"Reduce the skill size before saving."
            )
        self._ensure_open()
        await asyncio.to_thread(self._save_skill_sync, record)

    # Evolution lock operations
    @db_retry()
    def _set_evolution_lock_sync(self, skill_id: str, *, locked: bool) -> None:
        """Synchronous evolution lock update."""
        with self._mu:
            self._conn.execute(
                "UPDATE skills SET evolution_locked = ? WHERE skill_id = ?",
                (int(locked), skill_id),
            )
            self._conn.commit()

    async def set_evolution_lock(self, skill_id: str, *, locked: bool) -> None:
        """Lock or unlock a skill's auto-evolution.

        Locked skills are skipped by EvolutionScreener, protecting
        user-edited content from being overwritten by auto-evolution.

        Args:
            skill_id: Skill identifier
            locked: True to lock (block auto-evolution), False to unlock
        """
        self._ensure_open()
        await asyncio.to_thread(self._set_evolution_lock_sync, skill_id, locked=locked)

    @db_retry()
    def is_evolution_locked(self, skill_id: str) -> bool:
        """Check if a skill is locked from auto-evolution.

        Args:
            skill_id: Skill identifier

        Returns:
            True if locked, False if unlocked or skill not found
        """
        self._ensure_open()
        with self._reader() as conn:
            row = conn.execute("SELECT evolution_locked FROM skills WHERE skill_id = ?", (skill_id,)).fetchone()
            if not row:
                return False
            return bool(row["evolution_locked"])

    # Read operations (sync, use _reader())
    @db_retry()
    def get_skill(self, skill_id: str) -> SkillRecord | None:
        """Load skill by ID.

        Args:
            skill_id: Skill identifier

        Returns:
            SkillRecord or None if not found
        """
        self._ensure_open()
        with self._reader() as conn:
            row = conn.execute("SELECT * FROM skills WHERE skill_id = ?", (skill_id,)).fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def _row_to_record(self, sqlite_row: sqlite3.Row) -> SkillRecord:
        """Convert SQLite row to SkillRecord."""
        from myrm_agent_harness.agent.skills.evolution.core.types import (
            EnvironmentFingerprint,
            EvolutionType,
        )

        row = dict(sqlite_row)
        env_dict = json.loads(row["environment"]) if row.get("environment") else None

        return SkillRecord(
            skill_id=row["skill_id"],
            name=row["name"],
            description=row["description"],
            content=row["content"],
            path=row["path"],
            lineage=SkillLineage(
                evolution_type=EvolutionType(row["evolution_type"]),
                version=row["version"],
                parent_id=row["parent_id"],
                change_summary=row["change_summary"],
                created_at=datetime.fromisoformat(row["lineage_created_at"]),
                created_by=row["lineage_created_by"],
            ),
            verification_steps=json.loads(row.get("verification_steps", "[]")),
            eval_cases=json.loads(row.get("eval_cases", "[]")),
            environment=(EnvironmentFingerprint.from_dict(env_dict) if env_dict else None),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            is_active=bool(row["is_active"]),
            evolution_locked=bool(row.get("evolution_locked", 0)),
        )
