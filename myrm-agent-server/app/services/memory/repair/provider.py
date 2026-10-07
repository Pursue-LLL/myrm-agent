"""[POS]: app/services/memory/repair/provider.py
[INPUT]: Environment database settings and Harness MemoryRepairService contracts.
[OUTPUT]: Singleton MemoryRepairProvider lifecycle manager and dependency injection helper.
"""

import sqlite3
import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    CachePreservingCompactionBarrier,
    MemoryRepairService,
)


class MemoryRepairProvider:
    """Manages the server singleton instance of MemoryRepairService."""

    _instance: MemoryRepairService | None = None
    _custom_db_path: Path | None = None
    _conn: sqlite3.Connection | None = None
    _barrier: CachePreservingCompactionBarrier | None = None

    @classmethod
    def set_custom_db_path(cls, path: Path | None) -> None:
        """Override database path for isolated testing."""
        cls.reset()
        cls._custom_db_path = path

    @classmethod
    def get_service(cls) -> MemoryRepairService:
        """Return initialized MemoryRepairService singleton instance."""
        if cls._instance is None:
            if cls._custom_db_path:
                db_path = cls._custom_db_path
            else:
                base_dir = Path(tempfile.gettempdir()) / "myrm_data"
                base_dir.mkdir(parents=True, exist_ok=True)
                db_path = base_dir / "myrm_memories.db"

            cls._conn = sqlite3.connect(str(db_path), check_same_thread=False)
            cls._barrier = CachePreservingCompactionBarrier()
            cls._instance = MemoryRepairService(conn=cls._conn, barrier=cls._barrier)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton and close underlying connection."""
        if cls._conn:
            try:
                cls._conn.close()
            except sqlite3.DatabaseError:
                pass
        cls._conn = None
        cls._barrier = None
        cls._instance = None
        cls._custom_db_path = None


def get_memory_repair_service() -> MemoryRepairService:
    """FastAPI dependency injection provider for MemoryRepairService."""
    return MemoryRepairProvider.get_service()
