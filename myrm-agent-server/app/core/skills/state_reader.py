"""SkillStateReader implementation backed by SkillStore SQLite.

Bridges the harness SkillStateReader protocol with the evolution SkillStore,
resolving the database path from server configuration.
"""

import logging
from pathlib import Path

from myrm_agent_harness.agent.skills.evolution import SkillStore
from myrm_agent_harness.backends.skills.protocols import SkillStateReader

logger = logging.getLogger(__name__)


class SQLiteSkillStateReader(SkillStateReader):
    """Reads skill quarantine state from the evolution SkillStore SQLite."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path

    def _get_store(self) -> tuple[SkillStore, bool]:
        """Return (store, owns_connection).

        ``owns_connection=True`` only for an explicitly injected db_path, where
        the caller creates a dedicated short-lived store that must be closed.
        The default path returns the process-shared store (owned elsewhere), so
        hot read paths avoid paying connection setup, DDL replay, and a WAL
        checkpoint on every skill check.
        """
        if self._db_path is not None:
            return SkillStore(db_path=self._db_path), True
        from app.core.skills.store.evolution_store import get_evolution_skill_store

        return get_evolution_skill_store(), False

    def is_skill_active(self, skill_name: str) -> bool:
        store = None
        owns_connection = False
        try:
            store, owns_connection = self._get_store()
            record = store.get_skill(skill_name)
            return record.is_active if record else True
        except Exception as e:
            logger.error("Failed to check skill active status for %s: %s", skill_name, e)
            return True
        finally:
            if store is not None and owns_connection:
                store.close()
