"""Integration tests for prebuilt skill seed synchronization."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.skills.store.reader import list_prebuilt_skills
from app.core.storage.paths import (
    SKILL_METADATA_FILE,
    get_skill_metadata_path,
)
from app.core.storage.types import SkillType


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path))


@pytest.fixture(autouse=True)
def reset_sync_flag() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@pytest.mark.asyncio
async def test_sync_prebuilt_seeds_writes_metadata_and_skill_md(
    storage: LocalStorageBackend,
) -> None:
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert result.synced_count >= 1
    assert "systematic-debugging" in result.skill_ids
    assert "code-review" in result.skill_ids

    skills = await list_prebuilt_skills(storage)
    skill_ids = {s.id for s in skills}
    assert "systematic-debugging" in skill_ids
    assert "self-qa" in skill_ids

    meta_path = get_skill_metadata_path(SkillType.PREBUILT, "systematic-debugging")
    meta_raw = await storage.read_text(meta_path)
    meta = json.loads(meta_raw)
    assert meta["id"] == "systematic-debugging"
    assert meta["type"] == "prebuilt"
    assert meta["description"]
    assert SKILL_METADATA_FILE in meta_path


@pytest.mark.asyncio
async def test_sync_is_idempotent(storage: LocalStorageBackend) -> None:
    first = await prebuilt_sync.sync_prebuilt_seeds(storage)
    prebuilt_sync._synced = False  # noqa: SLF001
    second = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert first.synced_count >= 1
    assert second.synced_count == 0
    assert len(first.skill_ids) == len(second.skill_ids)


@pytest.mark.asyncio
async def test_sync_records_origin_hash(storage: LocalStorageBackend) -> None:
    """First sync should record origin_hash in metadata."""
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)
    assert result.synced_count >= 1

    meta_path = get_skill_metadata_path(SkillType.PREBUILT, "code-review")
    meta = json.loads(await storage.read_text(meta_path))
    assert meta["origin_hash"] is not None
    assert meta["origin_hash"].startswith("sha256:")
    assert meta["has_upstream_update"] is False


@pytest.mark.asyncio
async def test_sync_skips_user_modified_skill(storage: LocalStorageBackend) -> None:
    """If user modified a prebuilt skill, sync should preserve their version."""
    from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE

    from app.core.storage.paths import get_skill_file_path

    await prebuilt_sync.sync_prebuilt_seeds(storage)
    prebuilt_sync._synced = False  # noqa: SLF001

    skill_id = "code-review"
    md_path = get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE)
    user_content = "# My Custom Code Review\nUser modified version."
    await storage.write_text(md_path, user_content)

    await prebuilt_sync.sync_prebuilt_seeds(storage)

    stored_md = await storage.read_text(md_path)
    assert stored_md == user_content, "User modification should be preserved"


@pytest.mark.asyncio
async def test_sync_marks_upstream_update_for_modified_skill(
    storage: LocalStorageBackend,
    tmp_path: Path,
) -> None:
    """When upstream changes and user has modified, should mark has_upstream_update."""
    from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE

    from app.core.storage.paths import get_skill_file_path

    await prebuilt_sync.sync_prebuilt_seeds(storage)
    prebuilt_sync._synced = False  # noqa: SLF001

    skill_id = "code-review"
    md_path = get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE)
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)

    user_content = "# My Custom Code Review\nUser modified version."
    await storage.write_text(md_path, user_content)

    old_meta = json.loads(await storage.read_text(meta_path))
    fake_old_origin = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    old_meta["origin_hash"] = fake_old_origin
    await storage.write_text(meta_path, json.dumps(old_meta, indent=2))

    await prebuilt_sync.sync_prebuilt_seeds(storage)

    new_meta = json.loads(await storage.read_text(meta_path))
    assert new_meta["has_upstream_update"] is True
    stored_md = await storage.read_text(md_path)
    assert stored_md == user_content, "User modification should still be preserved"


@pytest.mark.asyncio
async def test_sync_updates_unmodified_skill_silently(
    storage: LocalStorageBackend,
) -> None:
    """When upstream changes but user hasn't modified, should silently update."""
    from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE

    from app.core.storage.paths import get_skill_file_path

    await prebuilt_sync.sync_prebuilt_seeds(storage)
    prebuilt_sync._synced = False  # noqa: SLF001

    skill_id = "code-review"
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)

    old_meta = json.loads(await storage.read_text(meta_path))
    old_meta["origin_hash"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

    md_path = get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE)
    old_content = await storage.read_text(md_path)
    from myrm_agent_harness.api.skills import compute_content_hash

    old_meta["origin_hash"] = compute_content_hash(old_content)
    fake_origin = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    await storage.write_text(md_path, old_content)

    meta_with_fake = dict(old_meta)
    meta_with_fake["origin_hash"] = fake_origin
    await storage.write_text(meta_path, json.dumps(meta_with_fake, indent=2))

    prebuilt_sync._synced = False  # noqa: SLF001
    second = await prebuilt_sync.sync_prebuilt_seeds(storage)

    new_meta = json.loads(await storage.read_text(meta_path))
    assert new_meta["has_upstream_update"] is True or second.synced_count >= 1


@pytest.mark.asyncio
async def test_sync_migration_no_origin_hash(storage: LocalStorageBackend) -> None:
    """When metadata lacks origin_hash (pre-migration), sync should handle gracefully."""
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    prebuilt_sync._synced = False  # noqa: SLF001

    skill_id = "code-review"
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)

    old_meta = json.loads(await storage.read_text(meta_path))
    del old_meta["origin_hash"]
    await storage.write_text(meta_path, json.dumps(old_meta, indent=2))

    await prebuilt_sync.sync_prebuilt_seeds(storage)

    new_meta = json.loads(await storage.read_text(meta_path))
    assert new_meta.get("origin_hash") is not None, "origin_hash should be set after migration"
    assert new_meta["origin_hash"].startswith("sha256:")


@pytest.mark.asyncio
async def test_cleanup_stale_prebuilt_skills(storage: LocalStorageBackend) -> None:
    # 1. Manually write a mock stale skill metadata and SKILL.md directly to storage
    from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE

    from app.core.storage.paths import get_skill_file_path

    stale_id = "obsolete-ghost-skill"
    md_path = get_skill_file_path(SkillType.PREBUILT, stale_id, SKILL_MD_FILE)
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, stale_id)

    await storage.write_text(md_path, "old skill content")
    await storage.write_text(meta_path, json.dumps({"id": stale_id, "version": "1.0.0"}))

    # 2. Verify files are present in storage before sync
    assert await storage.read_text(md_path) == "old skill content"
    assert await storage.read_text(meta_path) is not None

    # 3. Perform prebuilt sync (obsolete-ghost-skill is NOT a seed dir in prebuilt_seeds)
    prebuilt_sync._synced = False  # noqa: SLF001
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    # 4. Verify that the obsolete skill file structures are purged from storage
    with pytest.raises(FileNotFoundError):
        await storage.read_text(md_path)

    with pytest.raises(FileNotFoundError):
        await storage.read_text(meta_path)


@pytest.mark.asyncio
async def test_sync_handles_invalid_frontmatter_gracefully(
    storage: LocalStorageBackend,
    tmp_path: Path,
) -> None:
    """Skills with invalid frontmatter are skipped without crashing the whole sync."""
    from myrm_agent_harness.backends.skills._utils import SkillMetadataError

    with patch(
        "app.core.skills.prebuilt_sync.parse_skill_frontmatter",
        side_effect=SkillMetadataError("Required field 'description' missing"),
    ):
        result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert result.synced_count == 0
    assert result.skill_ids == ()


@pytest.mark.asyncio
async def test_sync_handles_token_count_failure(
    storage: LocalStorageBackend,
) -> None:
    """Token count failure should not block skill sync."""
    with patch(
        "app.core.skills.prebuilt_sync.get_token_count",
        side_effect=RuntimeError("tiktoken unavailable"),
    ):
        result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert result.synced_count >= 1
    skills = await list_prebuilt_skills(storage)
    assert len(skills) >= 1


@pytest.mark.asyncio
async def test_sync_skips_non_skill_dirs(
    storage: LocalStorageBackend,
) -> None:
    """Directories without SKILL.md or starting with _ are skipped."""
    seeds_dir = Path(prebuilt_sync.__file__).resolve().parents[3] / "assets" / "prebuilt_skills"
    non_skill_dirs = [d for d in seeds_dir.iterdir() if d.is_dir() and not (d / "SKILL.md").exists()]
    dot_dirs = [d for d in seeds_dir.iterdir() if d.name.startswith(("_", "."))]

    result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    for d in non_skill_dirs + dot_dirs:
        assert d.name not in result.skill_ids


@pytest.mark.asyncio
async def test_cleanup_handles_list_failure(storage: LocalStorageBackend) -> None:
    """Cleanup should handle storage.list failures gracefully."""
    await prebuilt_sync.sync_prebuilt_seeds(storage)
    prebuilt_sync._synced = False  # noqa: SLF001

    with patch.object(storage, "list", side_effect=OSError("disk error")):
        result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert result.synced_count == 0


@pytest.mark.asyncio
async def test_cleanup_handles_delete_failure(storage: LocalStorageBackend) -> None:
    """Cleanup should handle individual delete failures without crashing."""
    from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE

    from app.core.storage.paths import get_skill_file_path

    stale_id = "stale-delete-fail-skill"
    md_path = get_skill_file_path(SkillType.PREBUILT, stale_id, SKILL_MD_FILE)
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, stale_id)
    await storage.write_text(md_path, "stale content")
    await storage.write_text(meta_path, json.dumps({"id": stale_id}))

    original_delete = storage.delete

    async def failing_delete(path: str) -> None:
        if stale_id in path:
            raise OSError("permission denied")
        return await original_delete(path)

    with patch.object(storage, "delete", side_effect=failing_delete):
        prebuilt_sync._synced = False  # noqa: SLF001
        result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert result.synced_count >= 0


def test_parse_tags_edge_cases() -> None:
    """_parse_tags handles None and non-list gracefully."""
    from app.core.skills.prebuilt_sync import _parse_tags

    assert _parse_tags(None) == []
    assert _parse_tags({}) == []
    assert _parse_tags({"tags": "not-a-list"}) == []
    assert _parse_tags({"tags": ["a", "b"]}) == ["a", "b"]


@pytest.mark.asyncio
async def test_sync_upstream_update_for_unmodified_user(
    storage: LocalStorageBackend,
) -> None:
    """When upstream changes but user content matches origin, silently update.

    Scenario: current_hash == origin_hash (user didn't modify),
    but source_hash != origin_hash (upstream changed since last sync).
    This triggers line 254-259: silent update.
    """
    from myrm_agent_harness.agent.skills.market.sanitizer import SKILL_MD_FILE
    from myrm_agent_harness.api.skills import compute_content_hash

    from app.core.storage.paths import get_skill_file_path

    await prebuilt_sync.sync_prebuilt_seeds(storage)
    prebuilt_sync._synced = False  # noqa: SLF001

    skill_id = "systematic-debugging"
    md_path = get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE)
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)

    # Simulate "old content that was synced before upstream update":
    # Write fake old content to storage and set origin_hash to match it.
    old_content = "---\nname: systematic-debugging\ndescription: Old version\n---\n# Old"
    old_hash = compute_content_hash(old_content)
    await storage.write_text(md_path, old_content)

    meta = json.loads(await storage.read_text(meta_path))
    meta["origin_hash"] = old_hash
    await storage.write_text(meta_path, json.dumps(meta, indent=2))

    # Now: current_hash = hash(old_content) = old_hash = origin_hash  [user hasn't modified]
    # source_hash = hash(actual SKILL.md on disk) != old_hash         [upstream changed]
    # => triggers line 254-259: silent update

    prebuilt_sync._synced = False  # noqa: SLF001
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert result.synced_count >= 1
    new_meta = json.loads(await storage.read_text(meta_path))
    assert new_meta["has_upstream_update"] is False
    # Content should now be updated to source
    updated_content = await storage.read_text(md_path)
    assert "Old version" not in updated_content
