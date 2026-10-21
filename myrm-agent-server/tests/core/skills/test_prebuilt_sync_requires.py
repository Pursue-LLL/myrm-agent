"""The persisted prebuilt catalog must carry each seed's ``requires`` and agree with the runtime.

The Skills page reads ``_metadata.json`` snapshots written by ``sync_prebuilt_seeds``; the agent runtime
parses SKILL.md. Both feed the same availability gate, so the snapshot has to hold exactly what SKILL.md
declares, including snapshots written by earlier versions that predate the field.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills import StorageSkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata, SkillRequires, SkillTrust
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.skills.gates.oauth_availability import wrap_integration_oauth_backend
from app.core.skills.gates.requirements_availability import apply_requirements_availability_to_catalog
from app.core.skills.models import Skill
from app.core.skills.store.reader import list_prebuilt_skills
from app.core.skills.store.user_config import UserSkillConfigManager
from app.core.storage.paths import get_skill_file_path, get_skill_metadata_path
from app.core.storage.types import SkillType

NOTION = "notion-workspace"
EMPTY_REQUIRES = {"bins": [], "env": [], "config": []}
ENV_GATED_SEEDS = {
    NOTION: SkillRequires(env=["NOTION_API_KEY"]),
    "linear-project": SkillRequires(env=["LINEAR_API_KEY"]),
    "imap-smtp-email": SkillRequires(env=["EMAIL_IMAP_HOST", "EMAIL_IMAP_USER", "EMAIL_IMAP_PASSWORD"]),
    "xurl": SkillRequires(bins=["xurl"]),
}


@pytest.fixture(autouse=True)
def _fresh_prebuilt_sync() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalStorageBackend:
    backend = LocalStorageBackend(str(tmp_path))
    monkeypatch.setattr("app.core.skills.gates.requirements_availability.get_storage_provider", lambda: backend)
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    return backend


async def _sync_again(storage: LocalStorageBackend) -> None:
    prebuilt_sync._synced = False  # noqa: SLF001
    await prebuilt_sync.sync_prebuilt_seeds(storage)


async def _catalog(storage: LocalStorageBackend) -> dict[str, Skill]:
    return {skill.id: skill for skill in await list_prebuilt_skills(storage)}


async def _runtime(storage: LocalStorageBackend) -> dict[str, SkillMetadata]:
    backend = StorageSkillBackend(storage=storage, skills_prefix="skills/prebuilt", default_trust=SkillTrust.TRUSTED)
    return {meta.storage_skill_id or meta.name: meta for meta in await backend.list_skills()}


async def _read_metadata(storage: LocalStorageBackend, skill_id: str) -> dict[str, object]:
    return json.loads(await storage.read_text(get_skill_metadata_path(SkillType.PREBUILT, skill_id)))


async def _write_metadata(storage: LocalStorageBackend, skill_id: str, data: dict[str, object]) -> None:
    await storage.write_text(get_skill_metadata_path(SkillType.PREBUILT, skill_id), json.dumps(data, indent=2))


@pytest.mark.asyncio
async def test_catalog_snapshot_matches_runtime_for_every_seed(storage: LocalStorageBackend) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    catalog = await _catalog(storage)
    runtime = await _runtime(storage)

    assert catalog.keys() == runtime.keys()
    for skill_id, skill in catalog.items():
        meta = runtime[skill_id]
        assert skill.requires == (meta.requires or SkillRequires()), skill_id
        assert skill.primary_env == meta.primary_env, skill_id
        assert skill.always == meta.always, skill_id
        assert skill.model_invocable == meta.model_invocable, skill_id
        assert skill.user_invocable == meta.user_invocable, skill_id
        assert skill.allowed_domains == meta.allowed_domains, skill_id
        assert skill.allowed_tools == meta.allowed_tools, skill_id
        assert skill.config_schema == meta.config_schema, skill_id
        assert skill.evolution_locked == meta.evolution_locked, skill_id
        assert skill.required_oauth_issuers == meta.required_oauth_issuers, skill_id
        assert skill.required_mcp_server_ids == meta.required_mcp_server_ids, skill_id
        assert skill.required_permissions == [p.value for p in meta.required_permissions], skill_id


@pytest.mark.asyncio
async def test_catalog_snapshot_carries_declared_requirements(storage: LocalStorageBackend) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    catalog = await _catalog(storage)

    for skill_id, expected in ENV_GATED_SEEDS.items():
        assert catalog[skill_id].requires == expected, skill_id


@pytest.mark.asyncio
async def test_free_text_requires_stays_undeclared(storage: LocalStorageBackend) -> None:
    # blender-mcp writes ``requires`` as a human sentence, not the bins/env/config mapping.
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert (await _catalog(storage))["blender-mcp"].requires == SkillRequires()


@pytest.mark.asyncio
async def test_catalog_availability_follows_saved_keys_like_runtime(storage: LocalStorageBackend) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    async def verdicts() -> tuple[bool, bool]:
        skill = (await _catalog(storage))[NOTION]
        await apply_requirements_availability_to_catalog([skill])
        wrapped = wrap_integration_oauth_backend(
            StorageSkillBackend(storage=storage, skills_prefix="skills/prebuilt", default_trust=SkillTrust.TRUSTED)
        )
        runtime = {m.storage_skill_id: m for m in await wrapped.list_skills()}[NOTION]
        return skill.available, runtime.available

    assert await verdicts() == (False, False)

    manager = UserSkillConfigManager(storage)
    config = await manager.get_config()
    config.skill_env_vars = {NOTION: {"NOTION_API_KEY": "secret"}}
    await manager.save_config(config)

    assert await verdicts() == (True, True)


@pytest.mark.asyncio
async def test_resync_repairs_snapshots_written_without_requires(storage: LocalStorageBackend) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    pristine = await _read_metadata(storage, NOTION)
    await _write_metadata(storage, NOTION, {**pristine, "requires": EMPTY_REQUIRES})

    await _sync_again(storage)

    assert await _read_metadata(storage, NOTION) == pristine


@pytest.mark.asyncio
async def test_resync_repairs_user_modified_copy_from_its_own_skill_md(storage: LocalStorageBackend) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    pristine = await _read_metadata(storage, NOTION)
    skill_md_path = get_skill_file_path(SkillType.PREBUILT, NOTION, "SKILL.md")
    edited = (await storage.read_text(skill_md_path)).replace("NOTION_API_KEY", "MY_NOTION_TOKEN")
    await storage.write_text(skill_md_path, edited)
    await _write_metadata(storage, NOTION, {**pristine, "requires": EMPTY_REQUIRES})

    await _sync_again(storage)

    repaired = await _read_metadata(storage, NOTION)
    assert repaired["requires"] == {"bins": [], "env": ["MY_NOTION_TOKEN"], "config": []}
    assert repaired["origin_hash"] == pristine["origin_hash"]
    assert repaired["has_upstream_update"] is False
    assert await storage.read_text(skill_md_path) == edited


@pytest.mark.asyncio
async def test_snapshot_rewritten_for_upstream_update_still_reflects_the_user_copy(
    storage: LocalStorageBackend,
) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    pristine = await _read_metadata(storage, NOTION)
    skill_md_path = get_skill_file_path(SkillType.PREBUILT, NOTION, "SKILL.md")
    await storage.write_text(skill_md_path, (await storage.read_text(skill_md_path)).replace("NOTION_API_KEY", "MY_NOTION_TOKEN"))
    # An older bundled version was the baseline, so the sync flags an upstream update and rewrites the snapshot.
    await _write_metadata(storage, NOTION, {**pristine, "origin_hash": "0" * 64, "requires": EMPTY_REQUIRES})

    await _sync_again(storage)

    rewritten = await _read_metadata(storage, NOTION)
    assert rewritten["has_upstream_update"] is True
    assert rewritten["origin_hash"] == "0" * 64
    assert rewritten["requires"] == {"bins": [], "env": ["MY_NOTION_TOKEN"], "config": []}


@pytest.mark.asyncio
async def test_baseline_migration_of_a_user_copy_keeps_the_copy_requirements(storage: LocalStorageBackend) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    pristine = await _read_metadata(storage, NOTION)
    skill_md_path = get_skill_file_path(SkillType.PREBUILT, NOTION, "SKILL.md")
    await storage.write_text(skill_md_path, (await storage.read_text(skill_md_path)).replace("NOTION_API_KEY", "MY_NOTION_TOKEN"))
    legacy = {key: value for key, value in pristine.items() if key != "origin_hash"}
    await _write_metadata(storage, NOTION, {**legacy, "requires": EMPTY_REQUIRES})

    await _sync_again(storage)

    migrated = await _read_metadata(storage, NOTION)
    assert migrated["has_upstream_update"] is True
    assert migrated["requires"] == {"bins": [], "env": ["MY_NOTION_TOKEN"], "config": []}


@pytest.mark.asyncio
async def test_resync_leaves_snapshot_alone_when_user_copy_is_unparsable(storage: LocalStorageBackend) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    pristine = await _read_metadata(storage, NOTION)
    stale = {**pristine, "requires": EMPTY_REQUIRES}
    await _write_metadata(storage, NOTION, stale)
    await storage.write_text(get_skill_file_path(SkillType.PREBUILT, NOTION, "SKILL.md"), "no frontmatter at all")

    await _sync_again(storage)

    assert await _read_metadata(storage, NOTION) == stale


@pytest.mark.asyncio
async def test_resync_does_not_rewrite_current_snapshots(storage: LocalStorageBackend) -> None:
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    before = {skill_id: await _read_metadata(storage, skill_id) for skill_id in await _catalog(storage)}
    metadata_path = Path(storage.base_path) / get_skill_metadata_path(SkillType.PREBUILT, NOTION)
    mtime = metadata_path.stat().st_mtime_ns

    await _sync_again(storage)

    assert metadata_path.stat().st_mtime_ns == mtime
    assert {skill_id: await _read_metadata(storage, skill_id) for skill_id in before} == before
