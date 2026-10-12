"""Rehydrate ephemeral session deltas from Volume-backed SQLite before agent turns.

[POS]
app/services/memory/ephemeral_delta_hydration.py

[INPUT]
- Harness ephemeral_delta shared store + ContextBundle memory path

[OUTPUT]
- ensure_chat_ephemeral_deltas_hydrated: load tail deltas for an active chat_id
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
