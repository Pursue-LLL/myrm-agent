"""Unit tests for discovery install → user catalog enable helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult

from app.core.skills.discovery.mount import (
    DEFAULT_MOUNT_AGENT_ID,
    SkillMountResult,
    maybe_mount_after_install,
    resolve_mount_skill_id,
)


def test_resolve_mount_skill_id_from_local_path(tmp_path: Path) -> None:
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    result = SkillInstallResult(
        success=True,
        skill_name="demo-skill",
        skill_id="local::demo-skill",
        installed_path=str(skill_dir),
    )

    mount_id = resolve_mount_skill_id(result)
    assert mount_id is not None
    assert mount_id.startswith("local::")
    assert mount_id != "local::demo-skill"


def test_resolve_mount_skill_id_for_prebuilt() -> None:
    result = SkillInstallResult(
        success=True,
        skill_name="Official Skill",
        skill_id="official-skill",
        installed_path="prebuilt (already installed)",
    )
    assert resolve_mount_skill_id(result) == "official-skill"


@pytest.mark.asyncio
async def test_maybe_mount_after_install_enables_prebuilt() -> None:
    install_result = SkillInstallResult(
        success=True,
        skill_name="Official Skill",
        skill_id="official-skill",
        installed_path="prebuilt (already installed)",
    )

    with (
        patch(
            "app.core.skills.discovery.mount._is_skill_enabled",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.core.skills.discovery.mount._ensure_skill_enabled",
            new=AsyncMock(),
        ) as ensure_enabled,
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new=AsyncMock(),
        ) as get_agent,
        patch(
            "app.services.agent.agent_service.AgentService.update_agent",
            new=AsyncMock(),
        ) as update_agent,
        patch(
            "app.services.event.app_event_bus.get_event_bus",
        ) as mock_get_bus,
    ):
        mock_bus = mock_get_bus.return_value
        result = await maybe_mount_after_install(
            install_result,
            agent_id="builtin-general",
            mount_to_agent=True,
        )

    ensure_enabled.assert_awaited_once_with("official-skill")
    get_agent.assert_not_called()
    update_agent.assert_not_called()
    assert mock_bus.publish.called
    published_event = mock_bus.publish.call_args[0][0]
    assert published_event.event_type.value == "skill_pool_updated"
    assert published_event.data["action"] == "install"
    assert published_event.data["skill_id"] == "official-skill"
    assert result is not None
    assert result.mounted is True
    assert result.already_mounted is False
    assert result.mount_skill_id == "official-skill"


@pytest.mark.asyncio
async def test_maybe_mount_after_install_does_not_mutate_agent_profile(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    install_result = SkillInstallResult(
        success=True,
        skill_name="demo-skill",
        skill_id="local::demo-skill",
        installed_path=str(skill_dir),
    )

    with (
        patch(
            "app.core.skills.discovery.mount._is_skill_enabled",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.core.skills.discovery.mount._ensure_skill_enabled",
            new=AsyncMock(),
        ),
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new=AsyncMock(),
        ) as get_agent,
        patch(
            "app.services.agent.agent_service.AgentService.update_agent",
            new=AsyncMock(),
        ) as update_agent,
    ):
        result = await maybe_mount_after_install(
            install_result,
            agent_id=None,
            mount_to_agent=True,
        )

    get_agent.assert_not_called()
    update_agent.assert_not_called()
    assert result is not None
    assert result.mounted is True
    assert result.agent_id == DEFAULT_MOUNT_AGENT_ID


@pytest.mark.asyncio
async def test_maybe_mount_after_install_idempotent_when_already_enabled() -> None:
    install_result = SkillInstallResult(
        success=True,
        skill_name="Official Skill",
        skill_id="official-skill",
        installed_path="prebuilt (already installed)",
    )

    with (
        patch(
            "app.core.skills.discovery.mount._is_skill_enabled",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.core.skills.discovery.mount._ensure_skill_enabled",
            new=AsyncMock(),
        ) as ensure_enabled,
    ):
        result = await maybe_mount_after_install(
            install_result,
            agent_id="builtin-general",
            mount_to_agent=True,
        )

    ensure_enabled.assert_awaited_once_with("official-skill")
    assert result == SkillMountResult(
        mounted=True,
        agent_id="builtin-general",
        mount_skill_id="official-skill",
        already_mounted=True,
    )


@pytest.mark.asyncio
async def test_maybe_mount_after_install_skipped_when_mount_disabled() -> None:
    install_result = SkillInstallResult(
        success=True,
        skill_name="Official Skill",
        skill_id="official-skill",
        installed_path="prebuilt (already installed)",
    )

    with patch(
        "app.core.skills.discovery.mount._ensure_skill_enabled",
        new=AsyncMock(),
    ) as ensure_enabled:
        result = await maybe_mount_after_install(
            install_result,
            agent_id="builtin-general",
            mount_to_agent=False,
        )

    ensure_enabled.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_market_service_install_does_not_auto_enable_catalog() -> None:
    from app.core.skills.marketplace.market_service import market_service

    install_result = SkillInstallResult(
        success=True,
        skill_name="demo-skill",
        skill_id="local::demo-skill",
        installed_path="/tmp/demo-skill",
    )

    with (
        patch.object(
            market_service._base,
            "install",
            new=AsyncMock(return_value=install_result),
        ),
        patch(
            "app.core.skills.discovery.mount._ensure_skill_enabled",
            new=AsyncMock(),
        ) as ensure_enabled,
    ):
        result = await market_service.install("demo-skill", "clawhub")

    assert result.success
    ensure_enabled.assert_not_called()


@pytest.mark.asyncio
async def test_enable_after_install_included_in_empty_runtime_allowlist(
    tmp_path: Path,
) -> None:
    from myrm_agent_harness.backends.skills.local_skill_id import (
        local_skill_id_from_path,
    )

    from app.core.skills.effective_skill_ids import resolve_runtime_skill_ids
    from app.core.skills.models import UserSkillConfig

    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    catalog_skill_id = local_skill_id_from_path(skill_dir)
    install_result = SkillInstallResult(
        success=True,
        skill_name="demo-skill",
        skill_id="local::demo-skill",
        installed_path=str(skill_dir),
    )

    config = UserSkillConfig(user_id="test-user")

    async def fake_get_config() -> UserSkillConfig:
        return config

    async def fake_enable_local(skill_id: str) -> UserSkillConfig:
        if skill_id not in config.enabled_local_skill_ids:
            config.enabled_local_skill_ids.append(skill_id)
        return config

    with (
        patch(
            "app.core.skills.store.service.skills_service.user_config.get_config",
            new=AsyncMock(side_effect=fake_get_config),
        ),
        patch(
            "app.core.skills.store.service.skills_service.user_config.enable_local_skill",
            new=AsyncMock(side_effect=fake_enable_local),
        ),
        patch(
            "app.core.skills.config_version.bump_skill_config_version",
            new=lambda: None,
        ),
        patch(
            "app.core.skills.effective_skill_ids.skills_service.user_config.get_config",
            new=AsyncMock(side_effect=fake_get_config),
        ),
    ):
        mount_result = await maybe_mount_after_install(
            install_result,
            agent_id=None,
            mount_to_agent=True,
        )
        runtime_ids = await resolve_runtime_skill_ids([])

    assert mount_result is not None
    assert mount_result.mounted is True
    assert catalog_skill_id in runtime_ids
