"""Wire ephemeral delta SQLite persistence to the default Volume memory.db path.

[INPUT]
- myrm_agent_harness.toolkits.context_bundle::ContextBundleFacade (POS: Thin facade over existing Harness storage and volume paths; does not create a MemoryManager or import agent runtime modules.)
- myrm_agent_harness.toolkits.memory.ephemeral_delta.shared_store::configure_ephemeral_delta_persistence (POS: Single store instance so server EphemeralDeltaService and live agent middleware share session deltas.)
- app.config.settings::settings (POS: Aggregate exit of the settings package.)

[OUTPUT]
- ensure_default_volume_ephemeral_persistence: points the shared store at the Volume's `memory.db` (resolved from `settings.database.state_dir`); a repeated call with the same path changes nothing and a failure is logged and swallowed

[POS]
Persistence binding of the ephemeral delta suite: resolves the Volume's memory database and attaches it to the process-wide
delta store for the REST service and the agent paths.
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
