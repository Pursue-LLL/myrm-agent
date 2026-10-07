"""[POS]: app/services/memory/proactive_care/provider.py
[INPUT]: Local storage directories and ProactiveCareRebalancingService contracts from harness.
[OUTPUT]: ProactiveCareProvider singleton manager and FastAPI dependency injection helper.
"""

import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    ProactiveCareRebalancingService,
)


class ProactiveCareProvider:
    """Manages the server singleton instance of ProactiveCareRebalancingService."""

    _instance: ProactiveCareRebalancingService | None = None
    _custom_db_path: Path | None = None

    @classmethod
    def set_custom_db_path(cls, path: Path | None) -> None:
        """Override database path for isolated unit testing."""
        cls.reset()
        cls._custom_db_path = path

    @classmethod
    def get_service(cls) -> ProactiveCareRebalancingService:
        """Return initialized ProactiveCareRebalancingService singleton instance."""
        if cls._instance is None:
            if cls._custom_db_path:
                db_path = cls._custom_db_path
            else:
                base_dir = Path(tempfile.gettempdir()) / "myrm_data"
                base_dir.mkdir(parents=True, exist_ok=True)
                db_path = base_dir / "myrm_proactive_care.db"

            cls._instance = ProactiveCareRebalancingService(db_path=db_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance and safely close underlying database connections."""
        if cls._instance is not None:
            cls._instance.close()
        cls._instance = None
        cls._custom_db_path = None


def get_proactive_care_service() -> ProactiveCareRebalancingService:
    """FastAPI dependency injection provider for ProactiveCareRebalancingService."""
    return ProactiveCareProvider.get_service()
