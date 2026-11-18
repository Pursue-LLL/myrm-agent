"""Local-only HTTP fixtures for skill catalog Chrome E2E tests.

[INPUT]
- app.services.skills.growth.lifecycle::process_skill_review_result (POS: Skill growth lifecycle orchestration)
- app.core.skills.providers.local::compute_local_skill_id (POS: 本地技能扫描服务)
- app.core.skills.models::LOCAL_SKILLS_DIR (POS: Skill system data models)
- app.api.skills.drafts::get_skill_drafts (POS: 技能草稿 HTTP API：草稿列表、审批通过/拒绝、状态流转与前端刷新事件发布)
- app.services.approvals.registry::ApprovalRegistry (POS: 统一的拦截审批注册与唤醒中枢)

[OUTPUT]
- ensure_prebuilt_catalog: local/test route to seed prebuilt skills for Chrome E2E
- seed_skill_manage_mutation_batch: local/test route that leaves a skill whose second version came from a
  skill_mutation batch (real batch snapshot of the first), for the Task Steps rollback Chrome E2E
- seed_growth_skill / seed_review_result / cleanup_growth_skills: local/test routes for the draft approval
  Chrome E2E: a skill whose directory name and SKILL.md name the test chooses, a review result fed through the
  production growth lifecycle in place of the reviewer model's output, and removal of the directories the
  test created
- seed_test_mock_drafts / seed_mock_drafts_for_e2e: local/test route (and the helper behind it) that resets and
  seeds two predictable pending drafts for the Instinct Inbox Chrome E2E; a ``namespace`` keeps parallel runs from
  denying each other's seeds

[POS]
Dev-only skills fixture router for Chrome E2E (prebuilt catalog, skill-manage and upstream-update seeds, growth
drafts); gated by is_local_mode().
"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.toolkits.storage.factory import get_storage_provider
from pydantic import BaseModel, Field

from app.api.skills.drafts import get_skill_drafts
from app.config.deploy_mode import is_local_mode
from app.core.skills import prebuilt_sync
from app.core.skills.models import LOCAL_SKILLS_DIR
from app.core.skills.prebuilt_sync import sync_prebuilt_seeds
from app.core.skills.providers.local import compute_local_skill_id
from app.core.skills.replace.finalize import finalize_market_replace_success
from app.core.skills.replace.service import create_replace_snapshot
from app.core.skills.store.service import skills_service
from app.services.approvals.registry import ApprovalRegistry

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

    from app.core.storage.paths import get_skill_metadata_path
    from app.core.storage.types import SkillType

    storage = get_storage_provider()
    await sync_prebuilt_seeds(storage)
    skill_id = "systematic-debugging"
    skill = await skills_service.get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Prebuilt skill missing: {skill_id}")

    user_body = f"---\nname: systematic-debugging\ndescription: e2e upstream update\n---\n\n# Debug\n\n{_E2E_SCC_MARKER_V1}\n"
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


# A directory name the fixtures accept: one path component, so a test cannot write or remove outside the skills root.
_GrowthDirName = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")]


class SeedGrowthSkillRequest(BaseModel):
    dir_name: _GrowthDirName
    skill_name: str = Field(min_length=1, max_length=120)
    marker: str = Field(min_length=1, max_length=120)


class SeedReviewResultRequest(BaseModel):
    skill_name: str = Field(min_length=1, max_length=120)
    agent_id: str = Field(min_length=1, max_length=64)
    marker: str = Field(min_length=1, max_length=120)


class CleanupGrowthSkillsRequest(BaseModel):
    dir_names: list[_GrowthDirName] = Field(max_length=16)


def _write_growth_skill(directory: Path, skill_name: str, marker: str) -> None:
    directory.mkdir(parents=True)
    (directory / SKILL_MD_FILE).write_text(
        f"---\nname: {skill_name}\ndescription: Build the weekly report.\n---\n\n## Steps\n1. {marker}\n",
        encoding="utf-8",
    )


def _volume_ignores_case(directory: Path) -> bool:
    """Whether the volume opens ``directory`` under a name spelled in the other case."""
    return (directory.parent / directory.name.swapcase()).exists()


def _remove_growth_skills(dir_names: list[str]) -> list[str]:
    removed: list[str] = []
    for name in dir_names:
        target = LOCAL_SKILLS_DIR / name
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
            removed.append(name)
    return removed


@router.post("/test/seed-growth-skill", include_in_schema=False)
async def seed_growth_skill(body: SeedGrowthSkillRequest) -> dict[str, object]:
    """Local E2E: a skill whose directory name and SKILL.md name are chosen by the test, where the local scan lists it."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    directory = LOCAL_SKILLS_DIR / body.dir_name
    try:
        await asyncio.to_thread(_write_growth_skill, directory, body.skill_name, body.marker)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"Skill directory exists: {body.dir_name}") from exc
    return {
        "skill_id": compute_local_skill_id(directory),
        "volume_ignores_case": await asyncio.to_thread(_volume_ignores_case, directory),
    }


@router.post("/test/seed-review-result", include_in_schema=False)
async def seed_review_result(body: SeedReviewResultRequest) -> dict[str, bool]:
    """Local E2E: feed a review result for a new skill through the production growth lifecycle.

    The reviewer model's output is the one stage a test cannot choose; everything after it is the real pipeline
    (skill lookup, lock check, draft record), so the draft that lands in the inbox is the one production records.
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from app.services.skills.growth.lifecycle import process_skill_review_result

    draft = await process_skill_review_result(
        {
            "has_value": True,
            "type": "skill_draft",
            "user_id": "e2e-growth",
            "agent_id": body.agent_id,
            "skill_name": body.skill_name,
            "skill_description": "Build the weekly report.",
            "trigger_condition": "When the user asks for the weekly report.",
            "skill_steps": f"1. {body.marker}",
            "content": f"1. {body.marker}",
        }
    )
    return {"recorded": draft is not None}


@router.post("/test/cleanup-growth-skills", include_in_schema=False)
async def cleanup_growth_skills(body: CleanupGrowthSkillsRequest) -> dict[str, list[str]]:
    """Local E2E: remove skill directories a test created, by directory name."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    return {"removed": await asyncio.to_thread(_remove_growth_skills, body.dir_names)}


_TEST_MOCK_DRAFT_NAMES: tuple[str, str] = (
    "test-frontend-approve",
    "test-frontend-reject",
)


def _namespace_mock_names(namespace: str) -> tuple[str, str]:
    if not namespace.strip():
        return _TEST_MOCK_DRAFT_NAMES
    suffix = namespace.strip()[:16]
    return (
        f"test-frontend-approve-{suffix}",
        f"test-frontend-reject-{suffix}",
    )


async def seed_mock_drafts_for_e2e(agent_id: str = "default", namespace: str = "") -> dict[str, object]:
    """Create two predictable mock drafts for Instinct Inbox UI E2E tests.

    ``namespace`` isolates parallel Chrome E2E runs: mock names are suffixed and
    cleanup only touches drafts owned by the same namespace, so concurrent
    sessions never deny each other's seeds (SSOT: SHARED+NAMESPACE_WRITE).
    """
    approve_name, reject_name = _namespace_mock_names(namespace)
    names = (approve_name, reject_name)
    drafts, _ = await get_skill_drafts(status="PENDING_REVIEW", limit=500)
    for draft in drafts:
        if draft.name in names:
            await ApprovalRegistry.resolve_approval(draft.id, "deny")

    created_ids: list[str] = []
    mock_specs = (
        (
            approve_name,
            f"This is a test skill for UI Approve button ({approve_name}).",
            f'```markdown\n---\nname: {approve_name}\ndescription: "approve test"\n---\n\n# Rules\nApprove rules\n```',
            "Test draft approve UI",
        ),
        (
            reject_name,
            f"This is a test skill for UI Reject button ({reject_name}).",
            f'```markdown\n---\nname: {reject_name}\ndescription: "reject test"\n---\n\n# Rules\nReject rules\n```',
            "Test draft reject UI",
        ),
    )
    chat_id = f"test_chat_{namespace.strip()[:16]}" if namespace.strip() else "test_chat_123"
    for skill_name, description, content, reason in mock_specs:
        record = await ApprovalRegistry.create_approval(
            agent_id=agent_id,
            chat_id=chat_id,
            action_type="skill_draft",
            payload={
                "skill_name": skill_name,
                "description": description,
                "content": content,
                "score": 0.95,
            },
            reason=reason,
        )
        created_ids.append(record.id)

    return {"created_ids": created_ids, "skill_names": list(names)}


@router.post("/drafts/test/seed-mock", include_in_schema=False)
async def seed_test_mock_drafts(
    agent_id: str = "default",
    namespace: str = "",
) -> dict[str, object]:
    """Local dev/test only: reset and seed Instinct Inbox E2E mock drafts."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")
    return await seed_mock_drafts_for_e2e(agent_id=agent_id, namespace=namespace)
