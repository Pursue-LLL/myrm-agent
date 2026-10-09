"""[POS]: app/services/memory/tool_backup/provider.py
[INPUT]: Environment database settings and Harness ToolUseBackupService contracts.
[OUTPUT]: Singleton ToolUseBackupProvider lifecycle manager and dependency injection helper.
"""

import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    ToolUseBackupService,
)


class ToolUseBackupProvider:
    """Manages the server singleton instance of ToolUseBackupService."""

    _instance: ToolUseBackupService | None = None
    _custom_db_path: Path | None = None

    @classmethod
    def set_custom_db_path(cls, path: Path | None) -> None:
        """Override database path for isolated testing."""
        cls.reset()
        cls._custom_db_path = path

    @classmethod
    def get_service(cls) -> ToolUseBackupService:
        """Return initialized ToolUseBackupService singleton instance."""
        if cls._instance is None:
            if cls._custom_db_path:
                db_path = cls._custom_db_path
            else:
                base_dir = Path(tempfile.gettempdir()) / "myrm_data"
                base_dir.mkdir(parents=True, exist_ok=True)
                db_path = base_dir / "myrm_tool_uses.db"

            cls._instance = ToolUseBackupService(db_path=db_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton and close underlying connection."""
        if cls._instance is not None:
            cls._instance.close()
        cls._instance = None
        cls._custom_db_path = None


def get_tool_backup_service() -> ToolUseBackupService:
    """FastAPI dependency injection provider for ToolUseBackupService."""
    return ToolUseBackupProvider.get_service()
