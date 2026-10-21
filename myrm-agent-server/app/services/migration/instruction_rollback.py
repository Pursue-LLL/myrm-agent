"""Rollback competitor instruction-lane changes tied to a memory import batch.

[INPUT]
InstructionRollbackRecord from import batch metadata.

[OUTPUT]
rollback_instruction_for_batch: restore agent/global/rules for one import batch.

[POS]
Server-side companion to memory import ledger rollback for migration imports.
"""

from __future__ import annotations

import logging

from app.services.migration.instruction_writer import (
    instruction_rollback_record_from_metadata,
    rollback_instruction_plan,
)

logger = logging.getLogger(__name__)


async def rollback_instruction_for_batch_metadata(
    metadata: dict[str, object] | None,
    *,
    delete_imported_agent: bool = False,
) -> bool:
    """Rollback instruction lane changes when batch metadata contains a rollback record."""

    if not metadata:
        return False
    raw = metadata.get("instruction_rollback")
    if not isinstance(raw, dict):
        return False
    record = instruction_rollback_record_from_metadata(raw)
    if record is None:
        return False
    try:
        restored = await rollback_instruction_plan(record)
        if delete_imported_agent and record.agent_created:
            from app.services.agent.agent_service import AgentService

            await AgentService.delete_agent(record.target_agent_id)
        return restored
    except Exception as exc:
        logger.warning("Instruction rollback failed for agent %s: %s", record.target_agent_id, exc)
        return False
