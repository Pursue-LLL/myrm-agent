"""Local-only HTTP fixtures for skill catalog Chrome E2E tests."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

from app.config.deploy_mode import is_local_mode
from app.core.skills.prebuilt_sync import sync_prebuilt_seeds
from app.core.skills.store.service import skills_service

router = APIRouter()


@router.post("/test/ensure-prebuilt-catalog", include_in_schema=False)
async def ensure_prebuilt_catalog() -> dict[str, object]:
    """Local dev/test only: sync bundled prebuilt skills into catalog storage."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    storage = get_storage_provider()
    sync_result = await sync_prebuilt_seeds(storage)
    skill_ids = list(sync_result.skill_ids)
    if skill_ids:
        await skills_service.user_config.ensure_prebuilt_enabled_after_sync(skill_ids)

    return {
        "synced_count": len(skill_ids),
        "contains_systematic_debugging": "systematic-debugging" in skill_ids,
    }
