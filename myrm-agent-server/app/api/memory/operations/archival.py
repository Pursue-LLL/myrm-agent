"""Memory archival endpoints.

Provides API endpoints for automatic archival of old, rarely-accessed memories.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.memory.utils import get_memory_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/archival")


@router.post("/auto")
async def run_auto_archival(
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> dict[str, object]:
    """Automatically archive old, rarely-accessed memories.

    Archives memories that meet all criteria:
    - Age ≥ 180 days (6 months)
    - Access count ≤ 5 times
    - Importance ≤ 0.3 (low priority)

    Returns:
        Archival operation result with statistics
    """
    try:
        result = await memory_manager.archive_memories_auto()

        return {
            "success": True,
            "archived_count": result.archived_count,
            "duration_ms": result.duration_ms,
        }
    except Exception as e:
        logger.exception("Auto archival failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Auto archival failed: {e!s}",
        ) from e
