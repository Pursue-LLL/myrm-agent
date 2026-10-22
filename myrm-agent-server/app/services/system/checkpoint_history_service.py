"""Scheduled reclamation of superseded checkpoint history.

[INPUT]
- app.platform_utils::get_checkpointer (POS: process-wide checkpointer injected at startup)
- myrm_agent_harness.runtime.checkpointing.pruning::prune_checkpoint_history (POS: keep-latest pruning of any saver able to prune)

[OUTPUT]
- run_checkpoint_history_prune: one pruning pass over the live checkpointer that never raises

[POS]
Business entry point of the periodic job that keeps `checkpoints.db` from growing with conversation history no reader
loads: every agent step writes a full-state checkpoint, and only the newest checkpoint of a thread is ever resumed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.runtime.checkpointing.pruning import prune_checkpoint_history

from app.platform_utils import get_checkpointer

logger = logging.getLogger(__name__)


async def run_checkpoint_history_prune() -> bool:
    """Prune superseded checkpoint history once; False when the checkpointer cannot prune or the pass failed.

    A failed pass is only logged: pruning is housekeeping, and the next scheduled pass resumes where it stopped.
    """
    try:
        return await prune_checkpoint_history(get_checkpointer())
    except Exception:
        logger.warning("Checkpoint history prune failed; it is retried on the next schedule", exc_info=True)
        return False
