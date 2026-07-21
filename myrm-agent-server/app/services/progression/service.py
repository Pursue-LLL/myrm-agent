"""Progression service — CRUD for user progression data.

[INPUT]
- app.services.config.service::config_service (POS: config persistence layer)
- app.services.progression.schema (POS: data definitions)

[OUTPUT]
- get_progression / mark_milestone / compute_level functions

[POS]
Business logic for user milestone tracking. Uses UserConfig (config_key='user_progression')
for zero-migration persistence.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.services.config.service import config_service
from app.services.progression.schema import (
    MILESTONES,
    MilestoneRecord,
    ProgressionData,
    compute_level_from_milestones,
)

logger = logging.getLogger(__name__)

CONFIG_KEY = "user_progression"
_DEVICE_ID = "progression_service"


async def get_progression() -> ProgressionData:
    """Retrieve current progression data. Returns defaults if not yet stored."""
    record = await config_service.get(CONFIG_KEY)
    if record is None:
        return ProgressionData()
    try:
        return ProgressionData.model_validate(record.value)
    except Exception:
        logger.warning("Invalid progression data, returning defaults")
        return ProgressionData()


async def mark_milestone(milestone_id: str) -> ProgressionData:
    """Mark a milestone as completed. Idempotent — re-marking is a no-op.

    Returns updated progression data. Also triggers gate sync when level changes.
    """
    valid_ids = {m["id"] for m in MILESTONES}
    if milestone_id not in valid_ids:
        raise ValueError(f"Unknown milestone: {milestone_id}")

    data = await get_progression()

    if milestone_id in data.milestones and data.milestones[milestone_id].completed_at is not None:
        return data

    data.milestones[milestone_id] = MilestoneRecord(completed_at=datetime.now(UTC))

    old_level = data.current_level
    data.current_level = compute_level_from_milestones(data.milestones)

    await _persist(data)

    if data.current_level > old_level:
        from app.services.progression.gate_sync import sync_gates_for_level

        await sync_gates_for_level(data.current_level)

    return data


def compute_level(data: ProgressionData) -> int:
    """Compute level from progression data without side effects."""
    return compute_level_from_milestones(data.milestones)


async def _persist(data: ProgressionData) -> None:
    """Save progression data to UserConfig. Retries once on version conflict."""
    from app.services.config.service import VersionConflictError

    value = data.model_dump(mode="json")
    for _ in range(2):
        record = await config_service.get(CONFIG_KEY)
        try:
            if record is None:
                await config_service.set(CONFIG_KEY, value, device_id=_DEVICE_ID)
            else:
                await config_service.set(
                    CONFIG_KEY,
                    value,
                    device_id=_DEVICE_ID,
                    expected_version=record.version,
                )
            return
        except VersionConflictError:
            logger.debug("Progression persist: version conflict, retrying")
    logger.warning("Progression persist: gave up after retries")
