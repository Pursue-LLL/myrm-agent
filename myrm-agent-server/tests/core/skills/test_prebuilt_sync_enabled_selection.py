"""Which prebuilt skills are enabled after a sync: the curated defaults on a fresh install, the user's choice otherwise."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.skills.models import UserSkillConfig
from app.core.skills.store.user_config import (
    _DEFAULT_ENABLED_PREBUILT_SKILLS,
    UserSkillConfigManager,
)
from app.core.storage.paths import get_user_skill_config_path


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path))


@pytest.fixture(autouse=True)
def reset_sync_flag() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broken", ["{ not-json", "[]", "null", '"text"', "3"], ids=["not-json", "list", "null", "string", "number"]
)
async def test_corrupt_config_falls_back_without_clobbering_source(
    storage: LocalStorageBackend,
    broken: str,
) -> None:
    """损坏的配置（含合法 JSON 但不是对象）不能让技能子系统不可用，且原文件须保持原样供人工排查。"""
    config_path = get_user_skill_config_path()
    await storage.write_text(config_path, broken)

    config = await UserSkillConfigManager(storage).get_config()

    assert config.enabled_prebuilt_ids == []
    assert await storage.read_text(config_path) == broken


@pytest.mark.asyncio
async def test_ensure_prebuilt_enabled_new_user(storage: LocalStorageBackend) -> None:
    """A fresh install ships the curated default skill set, and only skills that exist."""
    prebuilt_sync._synced = False  # noqa: SLF001
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)
    manager = UserSkillConfigManager(storage)

    config = await manager.ensure_prebuilt_enabled_after_sync(list(result.skill_ids))

    assert config.enabled_prebuilt_ids == list(_DEFAULT_ENABLED_PREBUILT_SKILLS)
    assert set(config.enabled_prebuilt_ids) <= set(result.skill_ids)


@pytest.mark.asyncio
async def test_ensure_prebuilt_new_user_drops_missing_default_ids(
    storage: LocalStorageBackend,
) -> None:
    """A default skill missing upstream must not persist as a dead id."""
    prebuilt_sync._synced = False  # noqa: SLF001
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)
    manager = UserSkillConfigManager(storage)
    available = [sid for sid in result.skill_ids if sid not in _DEFAULT_ENABLED_PREBUILT_SKILLS]

    config = await manager.ensure_prebuilt_enabled_after_sync(list(available))

    assert config.enabled_prebuilt_ids == []


@pytest.mark.asyncio
async def test_ensure_prebuilt_never_overwrites_existing_selection(
    storage: LocalStorageBackend,
) -> None:
    """The curated default applies to fresh installs only; user choice always wins."""
    manager = UserSkillConfigManager(storage)
    await manager.save_config(UserSkillConfig(user_id="sandbox", enabled_prebuilt_ids=["self-qa"]))
    prebuilt_sync._synced = False  # noqa: SLF001
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    config = await manager.ensure_prebuilt_enabled_after_sync(list(result.skill_ids))

    assert config.enabled_prebuilt_ids == ["self-qa"]


@pytest.mark.asyncio
async def test_ensure_prebuilt_prunes_removed_skill_ids(storage: LocalStorageBackend) -> None:
    manager = UserSkillConfigManager(storage)
    await manager.save_config(
        UserSkillConfig(
            user_id="sandbox",
            enabled_prebuilt_ids=["self-qa", "removed-vendor-skill"],
            disabled_prebuilt_ids=["another-removed-skill"],
        )
    )

    config = await manager.ensure_prebuilt_enabled_after_sync(["self-qa", "code-review"])

    assert config.enabled_prebuilt_ids == ["self-qa"]
    assert config.disabled_prebuilt_ids == []


@pytest.mark.asyncio
async def test_ensure_prebuilt_respects_disabled_list(storage: LocalStorageBackend) -> None:
    manager = UserSkillConfigManager(storage)
    await manager.save_config(
        UserSkillConfig(
            user_id="sandbox",
            enabled_prebuilt_ids=["self-qa"],
            disabled_prebuilt_ids=["code-review"],
        )
    )

    await manager.ensure_prebuilt_enabled_after_sync(["self-qa", "code-review", "github-workflow"])
    config = await manager.get_config()

    assert config.enabled_prebuilt_ids == ["self-qa"]
    assert "github-workflow" not in config.enabled_prebuilt_ids
    assert "code-review" in config.disabled_prebuilt_ids
