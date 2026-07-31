"""Compounding playbook HTTP API.

[INPUT]
- app.services.compounding_playbook.status_service (POS: playbook status aggregation)
- myrm_agent_harness.toolkits.cron.manager::CronManager (POS: cron job source)

[OUTPUT]
- router: compounding playbook status REST routes

[POS]
HTTP boundary exposing compounding playbook readiness for settings UI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.memory import MemoryManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cron.routes.helpers import _get_manager as get_cron_manager
from app.database.connection import get_db
from app.schemas.compounding_playbook import CompoundingPlaybookStatusResponse
from app.services.compounding_playbook.status_service import build_compounding_status
from app.services.memory.manager_deps import get_crud_memory_manager

router = APIRouter(prefix="/compounding-playbook", tags=["compounding-playbook"])


@router.get("/status", response_model=CompoundingPlaybookStatusResponse)
async def get_compounding_playbook_status(
    agent_id: str | None = Query(None, max_length=128),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
    cron_manager: CronManager = Depends(get_cron_manager),
    db: AsyncSession = Depends(get_db),
) -> CompoundingPlaybookStatusResponse:
    """Return lightweight MSC compounding checklist counts for Settings UI."""
    return await build_compounding_status(
        memory_manager=memory_manager,
        cron_manager=cron_manager,
        agent_id=agent_id.strip() if agent_id else None,
        db=db,
    )
