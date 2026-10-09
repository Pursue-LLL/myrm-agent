"""[POS]: app/services/memory/cvfs/provider.py
[INPUT]: Local storage directories and ContextVirtualFileSystem contracts from harness.
[OUTPUT]: ContextVFSProvider singleton manager and FastAPI dependency injection helper.
"""

import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    ContextVirtualFileSystem,
)


class ContextVFSProvider:
    """Manages the server singleton instance of ContextVirtualFileSystem."""

    _instance: ContextVirtualFileSystem | None = None
    _custom_db_path: Path | None = None

    @classmethod
    def set_custom_db_path(cls, path: Path | None) -> None:
        """Override database path for isolated unit testing."""
        cls.reset()
        cls._custom_db_path = path

    @classmethod
    def get_vfs(cls) -> ContextVirtualFileSystem:
        """Return initialized ContextVirtualFileSystem singleton instance."""
        if cls._instance is None:
            if cls._custom_db_path:
                db_path = cls._custom_db_path
            else:
                base_dir = Path(tempfile.gettempdir()) / "myrm_data"
                base_dir.mkdir(parents=True, exist_ok=True)
                db_path = base_dir / "myrm_cvfs.db"

            cls._instance = ContextVirtualFileSystem(db_path=db_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance and safely close underlying connections."""
        if cls._instance is not None:
            cls._instance.close()
        cls._instance = None
        cls._custom_db_path = None


def get_context_vfs() -> ContextVirtualFileSystem:
    """FastAPI dependency injection provider for ContextVirtualFileSystem."""
    return ContextVFSProvider.get_vfs()
