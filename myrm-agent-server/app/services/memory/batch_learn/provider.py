"""[POS]: app/services/memory/batch_learn/provider.py
[INPUT]: Local storage directories and BatchMemoryLearningService contracts from harness.
[OUTPUT]: BatchMemoryLearningProvider singleton manager and FastAPI dependency injection helper.
"""

import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    BatchMemoryLearningService,
)


class BatchMemoryLearningProvider:
    """Manages the server singleton instance of BatchMemoryLearningService."""

    _instance: BatchMemoryLearningService | None = None
    _custom_db_path: Path | None = None

    @classmethod
    def set_custom_db_path(cls, path: Path | None) -> None:
        """Override database path for isolated unit testing."""
        cls.reset()
        cls._custom_db_path = path

    @classmethod
    def get_service(cls) -> BatchMemoryLearningService:
        """Return initialized BatchMemoryLearningService singleton instance."""
        if cls._instance is None:
            if cls._custom_db_path:
                db_path = cls._custom_db_path
            else:
                base_dir = Path(tempfile.gettempdir()) / "myrm_data"
                base_dir.mkdir(parents=True, exist_ok=True)
                db_path = base_dir / "myrm_batch_learn.db"

            cls._instance = BatchMemoryLearningService(db_path=db_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance and close database connections."""
        if cls._instance is not None:
            cls._instance.close()
        cls._instance = None
        cls._custom_db_path = None


def get_batch_learning_service() -> BatchMemoryLearningService:
    """FastAPI dependency injection provider for BatchMemoryLearningService."""
    return BatchMemoryLearningProvider.get_service()
