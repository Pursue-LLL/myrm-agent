"""Local-only HTTP fixtures for skill catalog Chrome E2E tests.

[OUTPUT]
- ensure_prebuilt_catalog: local/test route to seed prebuilt skills for Chrome E2E
- seed_skill_manage_mutation_batch: local/test route that leaves a skill whose second version came from a
  skill_mutation batch (real batch snapshot of the first), for the Task Steps rollback Chrome E2E

[POS]
Dev-only skills catalog fixture router; gated by is_local_mode().
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

from app.config.deploy_mode import is_local_mode
from app.core.skills.prebuilt_sync import sync_prebuilt_seeds
from app.core.skills.store.service import skills_service

router = APIRouter()

_E2E_MANAGE_MARKER_V1 = "e2e-skill-manage-batch-marker-v1"
_E2E_MANAGE_MARKER_V2 = "e2e-skill-manage-batch-marker-v2"


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


@router.post("/test/seed-skill-manage-mutation-batch", include_in_schema=False)
async def seed_skill_manage_mutation_batch() -> dict[str, object]:
    """Local E2E: skill_mutation batch snapshot + live v2 content for Task Steps rollback."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from app.services.skill_optimization.bootstrap import get_skill_optimization_storage
    from app.services.skill_optimization.rollback_service import RollbackService

    storage = get_storage_provider()
    await sync_prebuilt_seeds(storage)
    skill_id = "systematic-debugging"
    skill = await skills_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Prebuilt skill missing: {skill_id}")

    v1_body = f"---\nname: systematic-debugging\ndescription: e2e skill manage batch\n---\n\n# Debug\n\n{_E2E_MANAGE_MARKER_V1}\n"
    v2_body = f"---\nname: systematic-debugging\ndescription: e2e skill manage batch\n---\n\n# Debug\n\n{_E2E_MANAGE_MARKER_V2}\n"
    batch_id = str(uuid.uuid4())

    await skills_service.update_skill_file(skill_id, "SKILL.md", v1_body)
    opt_storage = get_skill_optimization_storage()
    async with opt_storage._get_session() as session:
        service = RollbackService(session)
        await service.insert_mutation_batch_snapshot(
            batch_id=batch_id,
            skill_id=skill_id,
            skill_content=v1_body,
            metadata={
                "batch_kind": "skill_mutation",
                "resource_files": {},
                "existed_before_batch": True,
            },
        )
    await skills_service.update_skill_file(skill_id, "SKILL.md", v2_body)

    return {
        "skill_id": skill_id,
        "skill_name": skill.name,
        "batch_id": batch_id,
        "marker_v1": _E2E_MANAGE_MARKER_V1,
        "marker_v2": _E2E_MANAGE_MARKER_V2,
        "fixture_id": uuid.uuid4().hex[:12],
    }
