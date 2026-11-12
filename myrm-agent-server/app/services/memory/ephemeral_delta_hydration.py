"""Rehydrate ephemeral session deltas from Volume-backed SQLite before agent turns.

[INPUT]
- myrm_agent_harness.toolkits.memory.ephemeral_delta.shared_store::ensure_ephemeral_deltas_hydrated (POS: Single store instance so server EphemeralDeltaService and live agent middleware share session deltas.)
- app.services.memory.ephemeral_delta_volume::ensure_default_volume_ephemeral_persistence (POS: Persistence binding of the ephemeral delta suite: resolves the Volume's memory database and attaches it to the process-wide delta store for the REST service and the agent paths.)

[OUTPUT]
- ensure_chat_ephemeral_deltas_hydrated: reloads a chat's persisted deltas into the shared store; a failure is logged and swallowed

[POS]
Turn-start hook of the ephemeral delta suite: before an agent turn it binds the shared store to the Volume database and reloads the
chat's deltas, so session overrides survive a server restart.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def ensure_chat_ephemeral_deltas_hydrated(chat_id: str | None) -> None:
    """Ensure in-flight session overrides are loaded after a server process restart."""
    normalized = (chat_id or "").strip()
    if not normalized:
        return
    try:
        from myrm_agent_harness.toolkits.memory.ephemeral_delta.shared_store import (
            ensure_ephemeral_deltas_hydrated,
        )

        from app.services.memory.ephemeral_delta_volume import (
            ensure_default_volume_ephemeral_persistence,
        )

        ensure_default_volume_ephemeral_persistence()
        ensure_ephemeral_deltas_hydrated(normalized)
    except Exception as exc:
        logger.warning(
            "Failed to hydrate ephemeral session deltas for chat %s: %s",
            normalized,
            exc,
        )
