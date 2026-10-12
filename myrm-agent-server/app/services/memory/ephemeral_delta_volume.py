"""Wire ephemeral delta SQLite persistence to the default Volume memory.db path.

[POS]
app/services/memory/ephemeral_delta_volume.py

[OUTPUT]
- ensure_default_volume_ephemeral_persistence: idempotent configure for CC/API/agent paths
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_default_volume_ephemeral_persistence() -> None:
    """Attach shared ephemeral delta store to the sandbox Volume relational DB."""
    try:
        from myrm_agent_harness.toolkits.context_bundle import ContextBundleFacade
        from myrm_agent_harness.toolkits.memory.ephemeral_delta.shared_store import (
            configure_ephemeral_delta_persistence,
        )

        from app.config.settings import settings

        facade = ContextBundleFacade.from_state_dir(
            settings.database.state_dir,
            ensure_layout=False,
        )
        db_path = Path(facade.memory_path()).resolve() / "memory.db"
        configure_ephemeral_delta_persistence(db_path)
    except Exception as exc:
        logger.warning("Failed to configure ephemeral delta persistence: %s", exc)
