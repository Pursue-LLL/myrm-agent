"""SkillStateReader implementation backed by SkillStore SQLite.

Bridges the harness SkillStateReader protocol with the evolution SkillStore,
resolving the database path from server configuration.
"""

import logging
from pathlib import Path

from myrm_agent_harness.agent.skills.evolution import SkillStore
from myrm_agent_harness.backends.skills.protocols import SkillStateReader

logger = logging.getLogger(__name__)


def _resolve_db_path() -> Path:
    from app.config.settings import settings

    return Path(settings.database.state_dir) / "skills.db"


class SQLiteSkillStateReader(SkillStateReader):
    """Reads skill quarantine state from the evolution SkillStore SQLite."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or _resolve_db_path()

    def is_skill_active(self, skill_name: str) -> bool:
        store = None
        try:
            store = SkillStore(db_path=self._db_path)
            record = store.get_skill(skill_name)
            return record.is_active if record else True
        except Exception as e:
            logger.error("Failed to check skill active status for %s: %s", skill_name, e)
            return True
        finally:
            if store:
                store.close()
