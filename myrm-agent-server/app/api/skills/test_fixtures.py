"""Local-only HTTP fixtures for skill catalog Chrome E2E tests.

[OUTPUT]
- ensure_prebuilt_catalog: local/test route to seed prebuilt skills for Chrome E2E
- seed_skill_manage_mutation_batch: local/test route that leaves a skill whose second version came from a
  skill_mutation batch (real batch snapshot of the first), for the Task Steps rollback Chrome E2E

[POS]
Dev-only skills catalog fixture router; gated by is_local_mode().
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

from app.config.deploy_mode import is_local_mode
from app.core.skills import prebuilt_sync
from app.core.skills.prebuilt_sync import sync_prebuilt_seeds
from app.core.skills.replace.finalize import finalize_market_replace_success
from app.core.skills.replace.service import create_replace_snapshot
from app.core.skills.store.service import skills_service

router = APIRouter()

_E2E_SCC_MARKER_V1 = "e2e-scc-replace-marker-v1"
_E2E_SCC_MARKER_V2 = "e2e-scc-replace-marker-v2"
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


@router.post("/test/seed-scc-market-replace", include_in_schema=False)
async def seed_scc_market_replace() -> dict[str, object]:
    """Local E2E: real replace snapshot + finalize on a disposable prebuilt skill."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    storage = get_storage_provider()
    await sync_prebuilt_seeds(storage)
    skill_id = "systematic-debugging"
    skill = await skills_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Prebuilt skill missing: {skill_id}")

    v1_body = f"---\nname: systematic-debugging\ndescription: e2e scc replace\n---\n\n# Debug\n\n{_E2E_SCC_MARKER_V1}\n"
    v2_body = f"---\nname: systematic-debugging\ndescription: e2e scc replace\n---\n\n# Debug\n\n{_E2E_SCC_MARKER_V2}\n"
    await skills_service.update_skill_file(skill_id, "SKILL.md", v1_body)

    batch_id, snapshot_truncated, snapshotted_paths = await create_replace_snapshot(
        skill.id,
        skill.name,
        batch_kind="e2e-market-replace",
    )
    await skills_service.update_skill_file(skill_id, "SKILL.md", v2_body)
    merged_truncated = await finalize_market_replace_success(
        skill.id,
        batch_id,
        snapshot_truncated=snapshot_truncated,
        snapshotted_paths=snapshotted_paths,
    )

    return {
        "skill_id": skill_id,
        "skill_name": skill.name,
        "pre_replace_batch_id": batch_id,
        "snapshot_truncated": merged_truncated,
        "marker_v1": _E2E_SCC_MARKER_V1,
        "marker_v2": _E2E_SCC_MARKER_V2,
        "fixture_id": uuid.uuid4().hex[:12],
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


@router.post("/test/seed-upstream-update-pending", include_in_schema=False)
async def seed_upstream_update_pending() -> dict[str, object]:
    """Local E2E: leave a prebuilt skill the reader modified while its bundled source moved on.

    The update-available state is what puts the "apply upstream update" control on screen, and
    the sync pass derives it from two hashes: the skill's stored ``origin_hash`` no longer
    matching the bundled source, while the stored content no longer matches ``origin_hash``
    either. Both conditions are facts this fixture writes directly, so the confirmation dialog
    it opens is the production one rather than a stubbed state.
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from app.core.skills.prebuilt_sync import SKILL_MD_FILE
    from app.core.storage.paths import get_skill_metadata_path
    from app.core.storage.types import SkillType

    storage = get_storage_provider()
    await sync_prebuilt_seeds(storage)
    skill_id = "systematic-debugging"
    skill = await skills_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Prebuilt skill missing: {skill_id}")

    user_body = (
        f"---\nname: systematic-debugging\ndescription: e2e upstream update\n---\n\n# Debug\n\n{_E2E_SCC_MARKER_V1}\n"
    )
    await skills_service.update_skill_file(skill_id, SKILL_MD_FILE, user_body)

    # The edit rewrites the skill's metadata, so the stale origin is written after it: the sync
    # pass reads `origin_hash` from this file, and only then can it see that the bundled source
    # moved on while the stored content is the reader's own.
    metadata_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)
    metadata = json.loads(await storage.read_text(metadata_path))
    metadata["origin_hash"] = "sha256:" + "0" * 64
    await storage.write_text(metadata_path, json.dumps(metadata, indent=2))

    # The sync pass runs once per process; a second fixture call in the same server would
    # otherwise return before it looks at the origin this fixture just wrote.
    prebuilt_sync._synced = False  # noqa: SLF001
    sync_result = await sync_prebuilt_seeds(storage)

    pending = await skills_service.get_skill(skill_id)
    return {
        "skill_id": skill_id,
        "skill_name": skill.name,
        "has_upstream_update": bool(pending and pending.has_upstream_update),
        "synced_count": sync_result.synced_count,
        "fixture_id": uuid.uuid4().hex[:12],
    }
