"""[POS]: app/services/memory/decontamination/provider.py
[INPUT]: Local storage directories and MemoryProvenanceDecontaminationService contracts from harness.
[OUTPUT]: MemoryDecontaminationProvider singleton manager and FastAPI dependency injection helper.
"""

import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    MemoryProvenanceDecontaminationService,
)


class MemoryDecontaminationProvider:
    """Manages the server singleton instance of MemoryProvenanceDecontaminationService."""

    _instance: MemoryProvenanceDecontaminationService | None = None
    _custom_db_path: Path | None = None

    @classmethod
    def set_custom_db_path(cls, path: Path | None) -> None:
        """Override database path for isolated unit testing."""
        cls.reset()
        cls._custom_db_path = path

    @classmethod
    def get_service(cls) -> MemoryProvenanceDecontaminationService:
        """Return initialized MemoryProvenanceDecontaminationService singleton instance."""
        if cls._instance is None:
            if cls._custom_db_path:
                db_path = cls._custom_db_path
            else:
                base_dir = Path(tempfile.gettempdir()) / "myrm_data"
                base_dir.mkdir(parents=True, exist_ok=True)
                db_path = base_dir / "myrm_decontamination.db"

            cls._instance = MemoryProvenanceDecontaminationService(db_path=db_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance and safely close underlying connections."""
        if cls._instance is not None:
            cls._instance.close()
        cls._instance = None
        cls._custom_db_path = None


def get_decontamination_service() -> MemoryProvenanceDecontaminationService:
    """FastAPI dependency injection provider for MemoryProvenanceDecontaminationService."""
    return MemoryDecontaminationProvider.get_service()
