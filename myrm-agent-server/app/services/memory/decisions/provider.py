"""[POS]: app/services/memory/decisions/provider.py
[INPUT]: Environment database settings and Harness EngineeringDecisionStore contracts.
[OUTPUT]: Singleton EngineeringDecisionProvider lifecycle manager.
"""

import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    EngineeringDecisionStore,
)


class EngineeringDecisionProvider:
    """Manages the server singleton instance of EngineeringDecisionStore."""

    _instance: EngineeringDecisionStore | None = None
    _custom_db_path: Path | None = None

    @classmethod
    def set_custom_db_path(cls, path: Path | None) -> None:
        """Override database path for isolated testing."""
        cls._custom_db_path = path
        cls._instance = None

    @classmethod
    def get_store(cls) -> EngineeringDecisionStore:
        """Return initialized EngineeringDecisionStore singleton instance."""
        if cls._instance is None:
            if cls._custom_db_path:
                db_path = cls._custom_db_path
            else:
                base_dir = Path(tempfile.gettempdir()) / "myrm_data"
                base_dir.mkdir(parents=True, exist_ok=True)
                db_path = base_dir / "engineering_decisions.db"

            cls._instance = EngineeringDecisionStore(db_path=db_path, auto_approve=False)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for teardown."""
        cls._instance = None
        cls._custom_db_path = None
