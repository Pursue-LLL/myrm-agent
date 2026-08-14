"""Integration tests for the test-audit prebuilt skill seed (no mocks).

Validates the full real pipeline for the test-audit asset: seed sync →
metadata persistence → user enablement → get_skills_by_ids resolution →
bundled-source restore. All assertions target the actual SKILL.md contract
(description, tags, report-only discipline) so the seed content is locked in.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from myrm_agent_harness.toolkits.storage.paths import (
    get_skill_file_path,
    get_skill_metadata_path,
)
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills import prebuilt_sync
from app.core.skills.store.service import SkillsService
from app.core.skills.store.user_config import UserSkillConfigManager

SKILL_ID = "test-audit"


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path))


@pytest.fixture(autouse=True)
def reset_sync_flag() -> None:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@pytest.fixture
def skills_service(storage: LocalStorageBackend) -> SkillsService:
    return SkillsService(storage=storage)


@pytest.mark.asyncio
async def test_seed_syncs_and_listed_with_report_only_contract(
    storage: LocalStorageBackend,
) -> None:
    """Sync → discovery: test-audit is present with its report-only description."""
    from app.core.skills.store.reader import list_prebuilt_skills

    result = await prebuilt_sync.sync_prebuilt_seeds(storage)
    assert SKILL_ID in result.skill_ids

    skills = await list_prebuilt_skills(storage)
    skill = next(s for s in skills if s.id == SKILL_ID)
    assert skill.storage_path
    assert "never writes tests" in skill.description


@pytest.mark.asyncio
async def test_metadata_persisted_from_frontmatter(storage: LocalStorageBackend) -> None:
    """Frontmatter fields (name/category/tags/version) land in metadata JSON."""
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    meta_path = get_skill_metadata_path(SkillType.PREBUILT, SKILL_ID)
    meta = json.loads(await storage.read_text(meta_path))

    assert meta["id"] == SKILL_ID
    assert meta["type"] == "prebuilt"
    assert meta["version"] == "1.0.0"
    assert meta["category"] == "development"
    assert {"testing", "coverage", "audit"} <= set(meta["tags"])
    assert "never writes tests" in meta["description"]
    assert meta["origin_hash"].startswith("sha256:")


@pytest.mark.asyncio
async def test_synced_skill_md_keeps_report_only_discipline(
    storage: LocalStorageBackend,
) -> None:
    """The stored SKILL.md retains the 'audits, does not write' contract."""
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    md_path = get_skill_file_path(SkillType.PREBUILT, SKILL_ID, SKILL_MD_FILE)
    stored = await storage.read_text(md_path)

    assert "This skill audits; it does not write." in stored
    assert "no test files exist at all" in stored


@pytest.mark.asyncio
async def test_user_enabled_and_resolvable(skills_service: SkillsService) -> None:
    """enablement → get_skills_by_ids / list_skills resolve the skill."""
    await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)
    manager = UserSkillConfigManager(skills_service.storage)
    await manager.ensure_prebuilt_enabled_after_sync([SKILL_ID])

    config = await manager.get_config()
    assert SKILL_ID in config.enabled_prebuilt_ids

    resolved = await skills_service.get_skills_by_ids([SKILL_ID])
    assert {s.id for s in resolved} == {SKILL_ID}
    assert resolved[0].type == SkillType.PREBUILT
    assert resolved[0].description

    listed = await skills_service.list_skills()
    prebuilt_ids = {s.id for s in listed if s.type.value == "prebuilt"}
    assert SKILL_ID in prebuilt_ids


@pytest.mark.asyncio
async def test_bundled_source_found_and_resettable(skills_service: SkillsService) -> None:
    """reset-to-default locates and restores the test-audit bundled source."""
    from app.api.skills.prebuilt import _find_seed_content, reset_prebuilt_to_default

    await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)

    source = _find_seed_content(SKILL_ID)
    assert source is not None
    assert "Audit the quality of an existing test suite" in source

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        result = await reset_prebuilt_to_default(SKILL_ID)

    assert result["status"] == "ok"
    assert SKILL_ID in result["message"]

    md_path = get_skill_file_path(SkillType.PREBUILT, SKILL_ID, SKILL_MD_FILE)
    restored = await skills_service.storage.read_text(md_path)
    assert "This skill audits; it does not write." in restored


@pytest.mark.asyncio
async def test_loads_through_agent_skill_backend(storage: LocalStorageBackend) -> None:
    """create_skill_backend exposes test-audit to the agent runtime."""
    from app.core.skills.loader import create_skill_backend

    service = SkillsService(storage=storage)
    with patch("app.core.skills.store.service.skills_service", service):
        backend = await create_skill_backend(storage=storage)

    skills = await backend.list_skills()
    names = {s.name for s in skills}
    assert SKILL_ID in names


@pytest.mark.asyncio
async def test_token_cost_persisted(storage: LocalStorageBackend) -> None:
    """Token estimate is persisted and positive for the test-audit seed."""
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    meta_path = get_skill_metadata_path(SkillType.PREBUILT, SKILL_ID)
    meta = json.loads(await storage.read_text(meta_path))
    assert isinstance(meta.get("token_cost"), int)
    assert meta["token_cost"] > 0
