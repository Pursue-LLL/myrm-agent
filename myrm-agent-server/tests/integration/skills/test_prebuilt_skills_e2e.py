"""End-to-end integration tests for prebuilt skill pipeline (no mocks on storage/sync).

Validates: seed sync → metadata discovery → user enablement → get_skills_by_ids
for BuiltIn Agent default bindings.
Also validates: reset-to-default and accept-upstream API logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
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
from app.services.agent.builtin_specs.builtin_initializer import _BUILTIN_AGENTS


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
    service = SkillsService(storage=storage)
    return service


@pytest.mark.asyncio
async def test_prebuilt_pipeline_lists_all_seeds(
    skills_service: SkillsService,
) -> None:
    """Full pipeline: sync seeds → list_prebuilt discovers all via metadata."""
    sync_result = await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)
    assert len(sync_result.skill_ids) >= 12

    await skills_service.user_config.ensure_prebuilt_enabled_after_sync(list(sync_result.skill_ids))

    listed = await skills_service.list_skills()
    prebuilt_ids = {s.id for s in listed if s.type.value == "prebuilt"}
    assert "systematic-debugging" in prebuilt_ids
    assert "code-review" in prebuilt_ids
    assert "test-driven-development" in prebuilt_ids


@pytest.mark.asyncio
async def test_builtin_developer_default_skills_resolvable(
    skills_service: SkillsService,
) -> None:
    """BuiltIn developer default_skill_ids resolve via get_skills_by_ids."""
    dev_spec = next(s for s in _BUILTIN_AGENTS if s.id == "builtin-developer")
    assert dev_spec.default_skill_ids

    await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)

    resolved = await skills_service.get_skills_by_ids(list(dev_spec.default_skill_ids))
    resolved_ids = {s.id for s in resolved}

    assert resolved_ids == set(dev_spec.default_skill_ids)
    for skill in resolved:
        assert skill.description
        assert skill.storage_path


@pytest.mark.asyncio
async def test_disable_prebuilt_persists_and_blocks_re_enable(
    storage: LocalStorageBackend,
) -> None:
    """Disable records disabled_prebuilt_ids; sync does not re-enable."""
    manager = UserSkillConfigManager(storage)
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    await manager.enable_prebuilt_skill("systematic-debugging")
    await manager.disable_prebuilt_skill("systematic-debugging")

    config = await manager.get_config()
    assert "systematic-debugging" not in config.enabled_prebuilt_ids
    assert "systematic-debugging" in config.disabled_prebuilt_ids

    await manager.ensure_prebuilt_enabled_after_sync(list(result.skill_ids))
    config_after = await manager.get_config()
    assert "systematic-debugging" not in config_after.enabled_prebuilt_ids


@pytest.mark.asyncio
async def test_create_skill_backend_loads_prebuilt(
    storage: LocalStorageBackend,
) -> None:
    """loader.create_skill_backend assembles prebuilt backend after sync."""
    from app.core.skills.loader import create_skill_backend

    service = SkillsService(storage=storage)
    with patch("app.core.skills.store.service.skills_service", service):
        backend = await create_skill_backend(storage=storage)

    skills = await backend.list_skills()
    names = {s.name for s in skills}
    assert "systematic-debugging" in names


@pytest.mark.asyncio
async def test_resolve_skill_env_map_with_real_backend(
    storage: LocalStorageBackend,
) -> None:
    """resolve_skill_env_map filters env against real installed prebuilt skills.

    Uses the real create_skill_backend pipeline (seed sync → StorageSkillBackend)
    with zero mocks on the backend. Verifies the self-healing contract:
    installed skill env is kept (keyed under its runtime name) and env for
    uninstalled skills is dropped.
    """
    from app.ai_agents.general_agent.config_builders import resolve_skill_env_map
    from app.core.skills.loader import create_skill_backend

    service = SkillsService(storage=storage)
    with patch("app.core.skills.store.service.skills_service", service):
        backend = await create_skill_backend(storage=storage)

    installed = await backend.list_skills()
    assert installed, "prebuilt seeds must be loaded through the real pipeline"
    real_name = installed[0].name

    env_vars = {
        real_name: {"GOOGLE_API_KEY": "test-key"},
        "nonexistent-skill-xyz": {"SECRET": "should-be-dropped"},
    }

    resolved = await resolve_skill_env_map(backend, env_vars)

    assert resolved == {real_name: {"GOOGLE_API_KEY": "test-key"}}
    assert "nonexistent-skill-xyz" not in resolved


@pytest.mark.asyncio
async def test_skill_env_vars_endpoints_persist_and_resolve(
    storage: LocalStorageBackend,
) -> None:
    """Full contract: API env endpoints (keyed by skill_id) → resolve_skill_env_map.

    The real WebUI saves env vars via PUT /skills/{skill_id}/env, which stores
    them under the skill_id key. get_skill_env_vars reads them back, and
    resolve_skill_env_map must match that stored key against installed skills
    via the runtime name so the agent runtime receives the env.
    """
    from app.ai_agents.general_agent.config_builders import resolve_skill_env_map
    from app.api.skills.config import (
        get_skill_env_vars,
        update_skill_env_vars,
    )
    from app.api.skills.schemas import UpdateSkillEnvVarsRequest
    from app.core.skills.loader import create_skill_backend

    service = SkillsService(storage=storage)
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    await service.user_config.ensure_prebuilt_enabled_after_sync(
        ["code-review", "systematic-debugging"]
    )

    with patch("app.api.skills.config.skills_service", service):
        saved = await update_skill_env_vars(
            "code-review",
            UpdateSkillEnvVarsRequest(env_vars={"GOOGLE_API_KEY": "test-key"}),
        )
        assert saved.env_vars == {"GOOGLE_API_KEY": "test-key"}

        loaded = await get_skill_env_vars("code-review")
        assert loaded.env_vars == {"GOOGLE_API_KEY": "test-key"}
        assert loaded.skill_id == "code-review"

    with patch("app.core.skills.store.service.skills_service", service):
        backend = await create_skill_backend(storage=storage)

    resolved = await resolve_skill_env_map(
        backend, {"code-review": {"GOOGLE_API_KEY": "test-key"}}
    )
    assert resolved == {"code-review": {"GOOGLE_API_KEY": "test-key"}}


@pytest.mark.asyncio
async def test_get_skill_env_vars_404_for_missing_skill(
    storage: LocalStorageBackend,
) -> None:
    """get_skill_env_vars raises 404 for a skill that does not exist."""
    from app.api.skills.config import get_skill_env_vars

    service = SkillsService(storage=storage)
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    with patch("app.api.skills.config.skills_service", service):
        with pytest.raises(HTTPException) as exc_info:
            await get_skill_env_vars("nonexistent-skill-xyz")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_skill_env_vars_404_for_missing_skill(
    storage: LocalStorageBackend,
) -> None:
    """update_skill_env_vars raises 404 for a skill that does not exist."""
    from app.api.skills.config import update_skill_env_vars
    from app.api.skills.schemas import UpdateSkillEnvVarsRequest

    service = SkillsService(storage=storage)
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    with patch("app.api.skills.config.skills_service", service):
        with pytest.raises(HTTPException) as exc_info:
            await update_skill_env_vars(
                "nonexistent-skill-xyz",
                UpdateSkillEnvVarsRequest(env_vars={"SECRET": "x"}),
            )
    assert exc_info.value.status_code == 404


# --- Prebuilt update management (reset-to-default / accept-upstream) ---


@pytest.mark.asyncio
async def test_reset_to_default_restores_bundled_content(
    skills_service: SkillsService,
) -> None:
    """reset_prebuilt_to_default restores original bundled content and clears flags."""
    from app.api.skills.prebuilt import _apply_bundled_source, _get_prebuilt_skill

    storage = skills_service.storage
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    skill_id = "code-review"
    md_path = get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE)
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)

    original_md = await storage.read_text(md_path)
    original_meta = json.loads(await storage.read_text(meta_path))
    original_hash = original_meta["origin_hash"]

    user_content = "# My Overridden Code Review\nCustom content here."
    await storage.write_text(md_path, user_content)
    original_meta["has_upstream_update"] = True
    await storage.write_text(meta_path, json.dumps(original_meta, indent=2))

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        skill = await _get_prebuilt_skill(skill_id)
        assert skill.has_upstream_update is True

        await _apply_bundled_source(skill, skill_id)

    restored_md = await storage.read_text(md_path)
    restored_meta = json.loads(await storage.read_text(meta_path))

    assert restored_md == original_md
    assert restored_meta["has_upstream_update"] is False
    assert restored_meta["origin_hash"] == original_hash


@pytest.mark.asyncio
async def test_accept_upstream_clears_flag(
    skills_service: SkillsService,
) -> None:
    """accept_prebuilt_upstream applies bundled source and clears has_upstream_update."""
    from app.api.skills.prebuilt import _apply_bundled_source, _get_prebuilt_skill

    storage = skills_service.storage
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    skill_id = "code-review"
    get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE)
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)

    meta = json.loads(await storage.read_text(meta_path))
    meta["has_upstream_update"] = True
    await storage.write_text(meta_path, json.dumps(meta, indent=2))

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        skill = await _get_prebuilt_skill(skill_id)
        assert skill.has_upstream_update is True

        await _apply_bundled_source(skill, skill_id)

    new_meta = json.loads(await storage.read_text(meta_path))
    assert new_meta["has_upstream_update"] is False
    assert new_meta["origin_hash"] is not None


@pytest.mark.asyncio
async def test_get_prebuilt_skill_404_for_nonexistent(
    skills_service: SkillsService,
) -> None:
    """_get_prebuilt_skill raises 404 for non-existent skill."""
    from app.api.skills.prebuilt import _get_prebuilt_skill

    await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        with pytest.raises(HTTPException) as exc_info:
            await _get_prebuilt_skill("nonexistent-skill-xyz")
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_apply_bundled_source_404_for_missing_seed(
    skills_service: SkillsService,
) -> None:
    """_apply_bundled_source raises 404 when bundled seed directory is missing."""
    from app.api.skills.prebuilt import _apply_bundled_source
    from app.core.skills.models import Skill

    fake_skill = Skill(
        id="fake-missing-seed",
        type=SkillType.PREBUILT,
        name="fake-missing-seed",
        description="test",
        storage_path="skills/prebuilt/fake-missing-seed",
    )

    with pytest.raises(HTTPException) as exc_info:
        await _apply_bundled_source(fake_skill, "fake-missing-seed")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_reset_to_default_endpoint_returns_ok(
    skills_service: SkillsService,
) -> None:
    """reset_prebuilt_to_default endpoint returns proper status and message."""
    from app.api.skills.prebuilt import reset_prebuilt_to_default

    await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        result = await reset_prebuilt_to_default("code-review")

    assert result["status"] == "ok"
    assert "code-review" in result["message"]


@pytest.mark.asyncio
async def test_accept_upstream_endpoint_rejects_no_pending(
    skills_service: SkillsService,
) -> None:
    """accept_prebuilt_upstream rejects when has_upstream_update is False."""
    from app.api.skills.prebuilt import accept_prebuilt_upstream

    await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        with pytest.raises(HTTPException) as exc_info:
            await accept_prebuilt_upstream("code-review")
        assert exc_info.value.status_code == 400
        assert "No upstream update pending" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_accept_upstream_endpoint_succeeds_with_pending(
    skills_service: SkillsService,
) -> None:
    """accept_prebuilt_upstream succeeds when has_upstream_update is True."""
    from app.api.skills.prebuilt import accept_prebuilt_upstream

    storage = skills_service.storage
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    skill_id = "code-review"
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)
    meta = json.loads(await storage.read_text(meta_path))
    meta["has_upstream_update"] = True
    await storage.write_text(meta_path, json.dumps(meta, indent=2))

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        result = await accept_prebuilt_upstream(skill_id)

    assert result["status"] == "ok"
    assert skill_id in result["message"]

    new_meta = json.loads(await storage.read_text(meta_path))
    assert new_meta["has_upstream_update"] is False


@pytest.mark.asyncio
async def test_tdd_skill_v120_contract_guard(
    skills_service: SkillsService,
) -> None:
    """test-driven-development v1.2.0 enhanced contract fields survive the pipeline.

    Guards the v1.2.0 enhancement (VERIFY/mutation-check step, independent
    expectation derivation, two new potential traps, deeper reference file)
    against regression.
    """
    from myrm_agent_harness.api.skills import parse_skill_frontmatter

    sync_result = await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)
    assert "test-driven-development" in sync_result.skill_ids

    md_path = get_skill_file_path(
        SkillType.PREBUILT, "test-driven-development", SKILL_MD_FILE
    )
    content = await skills_service.storage.read_text(md_path)
    fm = parse_skill_frontmatter(content, "test-driven-development")

    assert fm.version == "1.2.0"
    assert fm.contract is not None
    assert len(fm.contract.steps) == 5
    assert any("PRIORITIZE" in step for step in fm.contract.steps)
    assert any("VERIFY" in step for step in fm.contract.steps)
    assert {v.step_id for v in fm.contract.verification_steps} >= {
        "test_fails_first",
        "minimal_green",
        "tests_assert_behavior",
        "expectations_derived_independently",
        "mutation_check_covered",
    }
    trap_descriptions = {t.description for t in fm.contract.potential_traps}
    assert any("Mocking everything" in d for d in trap_descriptions)
    assert any("end-to-end tests" in d for d in trap_descriptions)
    assert any("mirror assertion" in d for d in trap_descriptions)
    assert any("constants or private structure" in d for d in trap_descriptions)
    assert "derived independently" in fm.contract.success_criteria

    body = content.split("---", 2)[-1]
    for heading in (
        "## Writing Good Tests",
        "### Prefer Real Over Mocks",
        "### Test State, Not Interactions",
        "### Test Pyramid",
        "### Derive Expectations Independently",
        "### No Change Detectors",
        "### Mutation Check",
        "### Avoid Horizontal Slices",
        "### Gate Function",
        "### Deeper Reference",
    ):
        assert heading in body, f"missing v1.2.0 body section: {heading}"
    assert '"The source text changed"' in body, "missing Gate Function 4th branch"
    assert "run the artifact and assert its effects" in body
    assert '"The test passes immediately"' in body, "missing Red Flags test-passes-immediately"
    assert "Fix the test to fail first" in body

    ref_path = get_skill_file_path(
        SkillType.PREBUILT,
        "test-driven-development",
        "references/writing-good-tests.md",
    )
    ref_content = await skills_service.storage.read_text(ref_path)
    for section in (
        "## Behavior, Not Text",
        "## Your Code, Not the Framework",
        "## Mock Discipline",
        "## Quick Reference",
        "## Warning Signs",
        "## Rationalizations",
        "## When Stuck",
    ):
        assert section in ref_content, f"missing v1.2.0 reference section: {section}"
    assert 'Mocking "just to be safe"' in ref_content, "missing Warning Signs 11th item"
    assert "wished-for API" in ref_content, "missing When Stuck wished-for API"
    assert "Sunk cost" in ref_content, "missing Rationalizations sunk cost row"


@pytest.mark.asyncio
async def test_evidence_discipline_synced_and_economy_bound(
    skills_service: SkillsService,
) -> None:
    """evidence-discipline seed syncs and builtin-economy default binding resolves.

    Full pipeline with no mocks on storage or sync: seed sync → metadata
    discovery → get_skills_by_ids for the builtin-economy default binding.
    """
    economy_spec = next(s for s in _BUILTIN_AGENTS if s.id == "builtin-economy")
    assert "evidence-discipline" in economy_spec.default_skill_ids

    sync_result = await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)
    assert "evidence-discipline" in sync_result.skill_ids

    resolved = await skills_service.get_skills_by_ids(["evidence-discipline"])
    assert {s.id for s in resolved} == {"evidence-discipline"}
    skill = resolved[0]
    assert skill.description
    assert skill.storage_path
    assert skill.type == SkillType.PREBUILT
