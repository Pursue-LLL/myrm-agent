"""Integration: discovery install → catalog enable → runtime skill IDs (SSOT).

Mocks only external market download/update paths (_base.install,
SkillAutoUpdateChecker.update_skill). enable, user config, runtime resolution,
and failure response assembly run without mocks.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.backends.skills.local_skill_id import local_skill_id_from_path
from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult
from myrm_agent_harness.backends.skills.scanning.archive_security import (
    ArchiveSecurityCode,
)
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.api.skills import discovery
from app.core.skills.effective_skill_ids import resolve_runtime_skill_ids
from app.core.skills.marketplace.market_service import market_service
from app.core.skills.store.service import SkillsService


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path))


@pytest.fixture(autouse=True)
def bind_skills_service(storage: LocalStorageBackend) -> SkillsService:
    service = SkillsService(storage=storage)
    with (
        patch("app.core.skills.store.service.skills_service", service),
        patch("app.core.skills.effective_skill_ids.skills_service", service),
    ):
        yield service


@pytest.fixture
def discovery_client() -> TestClient:
    app = FastAPI(title="Discovery Install Integration")
    app.include_router(discovery.router, prefix="/api/v1/skills")
    return TestClient(app)


def _local_install_result(skill_dir: Path) -> SkillInstallResult:
    return SkillInstallResult(
        success=True,
        skill_name=skill_dir.name,
        skill_id=f"local::{skill_dir.name}",
        installed_path=str(skill_dir),
    )


@pytest.mark.asyncio
async def test_install_api_enables_catalog_and_runtime_includes_skill(
    storage: LocalStorageBackend,
    discovery_client: TestClient,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\n---\n"
    )
    catalog_id = local_skill_id_from_path(skill_dir)

    with (
        patch.object(
            market_service._base,
            "install",
            new=AsyncMock(return_value=_local_install_result(skill_dir)),
        ),
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new=AsyncMock(),
        ),
        patch(
            "app.services.agent.agent_service.AgentService.update_agent",
            new=AsyncMock(),
        ) as update_agent,
        patch(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            new=AsyncMock(),
        ),
        patch("app.api.skills.discovery._audit_skill_action"),
    ):
        response = discovery_client.post(
            "/api/v1/skills/discovery/install",
            json={
                "skill_id": "demo-skill",
                "source": "clawhub",
                "mount_to_agent": True,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["mounted"] is True
    assert body["mount_error"] == ""

    from app.core.skills.store.service import skills_service

    user_config = await skills_service.user_config.get_config()
    assert catalog_id in user_config.enabled_local_skill_ids

    runtime_ids = await resolve_runtime_skill_ids([])
    assert catalog_id in runtime_ids

    update_agent.assert_not_called()
    assert body.get("allowlist_appended") is False


@pytest.mark.asyncio
async def test_install_api_skips_enable_when_mount_disabled(
    discovery_client: TestClient,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "keep-disabled"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: keep-disabled\ndescription: x\n---\n"
    )
    catalog_id = local_skill_id_from_path(skill_dir)

    with (
        patch.object(
            market_service._base,
            "install",
            new=AsyncMock(return_value=_local_install_result(skill_dir)),
        ),
        patch(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
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
        patch("app.api.skills.discovery._audit_skill_action"),
    ):
        response = discovery_client.post(
            "/api/v1/skills/discovery/install",
            json={
                "skill_id": "keep-disabled",
                "source": "clawhub",
                "mount_to_agent": False,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["mounted"] is False
    assert body.get("allowlist_appended") is False
    assert body.get("allowlist_append_error") in ("", None)
    get_agent.assert_not_awaited()
    update_agent.assert_not_awaited()

    from app.core.skills.store.service import skills_service

    user_config = await skills_service.user_config.get_config()
    assert catalog_id not in user_config.enabled_local_skill_ids

    runtime_ids = await resolve_runtime_skill_ids([])
    assert catalog_id not in runtime_ids


@pytest.mark.asyncio
async def test_install_from_url_enables_catalog(
    discovery_client: TestClient,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "url-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: url-skill\ndescription: u\n---\n")
    catalog_id = local_skill_id_from_path(skill_dir)

    with (
        patch.object(
            market_service._base,
            "install_from_url",
            new=AsyncMock(return_value=_local_install_result(skill_dir)),
        ),
        patch(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            new=AsyncMock(),
        ),
        patch("app.api.skills.discovery._audit_skill_action"),
    ):
        response = discovery_client.post(
            "/api/v1/skills/discovery/install-from-url",
            json={"url": "https://github.com/example/repo", "mount_to_agent": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["mounted"] is True

    from app.core.skills.store.service import skills_service

    user_config = await skills_service.user_config.get_config()
    assert catalog_id in user_config.enabled_local_skill_ids


@pytest.mark.asyncio
async def test_update_api_enables_catalog_after_reinstall(
    discovery_client: TestClient,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "update-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: update-skill\ndescription: u\n---\n"
    )
    catalog_id = local_skill_id_from_path(skill_dir)

    with (
        patch.object(
            market_service._base,
            "install",
            new=AsyncMock(return_value=_local_install_result(skill_dir)),
        ),
        patch(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            new=AsyncMock(),
        ),
        patch("app.api.skills.discovery._audit_skill_action"),
    ):
        response = discovery_client.post(
            "/api/v1/skills/discovery/update",
            json={
                "skill_name": "update-skill",
                "skill_id": "update-skill",
                "source": "clawhub",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["mounted"] is True

    from app.core.skills.store.service import skills_service

    user_config = await skills_service.user_config.get_config()
    assert catalog_id in user_config.enabled_local_skill_ids


@pytest.mark.asyncio
async def test_prebuilt_install_enables_catalog(
    discovery_client: TestClient,
) -> None:
    prebuilt_id = "systematic-debugging"
    install_result = SkillInstallResult(
        success=True,
        skill_name="Systematic Debugging",
        skill_id=prebuilt_id,
        installed_path="prebuilt (already installed)",
    )

    with (
        patch.object(
            market_service._base,
            "install",
            new=AsyncMock(return_value=install_result),
        ),
        patch(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            new=AsyncMock(),
        ),
        patch("app.api.skills.discovery._audit_skill_action"),
    ):
        response = discovery_client.post(
            "/api/v1/skills/discovery/install",
            json={
                "skill_id": prebuilt_id,
                "source": "prebuilt",
                "mount_to_agent": True,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["mounted"] is True
    assert body["mount_skill_id"] == prebuilt_id

    from app.core.skills.store.service import skills_service

    user_config = await skills_service.user_config.get_config()
    assert prebuilt_id in user_config.enabled_prebuilt_ids

    runtime_ids = await resolve_runtime_skill_ids([])
    assert prebuilt_id in runtime_ids


@pytest.mark.asyncio
async def test_install_idempotent_reports_already_enabled(
    discovery_client: TestClient,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "idem-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: idem-skill\ndescription: i\n---\n")

    with (
        patch.object(
            market_service._base,
            "install",
            new=AsyncMock(return_value=_local_install_result(skill_dir)),
        ),
        patch(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            new=AsyncMock(),
        ),
        patch("app.api.skills.discovery._audit_skill_action"),
    ):
        first = discovery_client.post(
            "/api/v1/skills/discovery/install",
            json={
                "skill_id": "idem-skill",
                "source": "clawhub",
                "mount_to_agent": True,
            },
        )
        second = discovery_client.post(
            "/api/v1/skills/discovery/install",
            json={
                "skill_id": "idem-skill",
                "source": "clawhub",
                "mount_to_agent": True,
            },
        )

    assert first.json()["mounted"] is True
    assert first.json()["mount_already_present"] is False
    assert second.json()["mounted"] is True
    assert second.json()["mount_already_present"] is True


@pytest.mark.asyncio
async def test_explicit_allowlist_takes_precedence_over_catalog() -> None:
    from app.core.skills.store.service import skills_service

    explicit_id = "prebuilt::only-one"
    await skills_service.user_config.enable_prebuilt_skill("systematic-debugging")
    await skills_service.user_config.enable_prebuilt_skill("code-review")

    runtime = await resolve_runtime_skill_ids([explicit_id])
    assert runtime == [explicit_id]


@pytest.mark.asyncio
async def test_install_failure_passes_error_and_error_code(
    discovery_client: TestClient,
) -> None:
    """安装失败时，API 响应必须透传 success/error/error_code，且不触发 mount/audit。

    Mock 仅限外部市场下载（_base.install）；失败响应组装、mount 跳过、catalog 不变全真实。
    """
    failed_result = SkillInstallResult(
        success=False,
        skill_name="evil-skill",
        skill_id="local::evil-skill",
        installed_path="",
        error="Skill contains executable binary content which is not allowed.",
        error_code=ArchiveSecurityCode.EXECUTABLE_BINARY_DETECTED.value,
    )
    with (
        patch.object(
            market_service._base,
            "install",
            new=AsyncMock(return_value=failed_result),
        ),
        patch(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            new=AsyncMock(),
        ),
        patch("app.api.skills.discovery._audit_skill_action") as audit,
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new=AsyncMock(),
        ) as get_agent,
        patch(
            "app.services.agent.agent_service.AgentService.update_agent",
            new=AsyncMock(),
        ) as update_agent,
    ):
        response = discovery_client.post(
            "/api/v1/skills/discovery/install",
            json={
                "skill_id": "evil-skill",
                "source": "clawhub",
                "mount_to_agent": True,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == failed_result.error
    assert body["error_code"] == failed_result.error_code
    assert body["mounted"] is False
    audit.assert_not_called()
    get_agent.assert_not_awaited()
    update_agent.assert_not_awaited()

    from app.core.skills.store.service import skills_service

    user_config = await skills_service.user_config.get_config()
    assert "local::evil-skill" not in user_config.enabled_local_skill_ids
    runtime_ids = await resolve_runtime_skill_ids([])
    assert "local::evil-skill" not in runtime_ids


@pytest.mark.asyncio
async def test_install_from_url_failure_passes_error_and_error_code(
    discovery_client: TestClient,
) -> None:
    """install-from-url 失败时同样透传 error_code（与 install 端点共享失败组装契约）。"""
    failed_result = SkillInstallResult(
        success=False,
        skill_name="",
        skill_id="",
        installed_path="",
        error="Repository not found.",
        error_code="",
    )
    with (
        patch.object(
            market_service._base,
            "install_from_url",
            new=AsyncMock(return_value=failed_result),
        ),
        patch(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            new=AsyncMock(),
        ),
        patch("app.api.skills.discovery._audit_skill_action") as audit,
    ):
        response = discovery_client.post(
            "/api/v1/skills/discovery/install-from-url",
            json={"url": "https://github.com/missing/repo", "mount_to_agent": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == failed_result.error
    assert body["error_code"] == ""
    assert body["mounted"] is False
    audit.assert_not_called()


@pytest.mark.asyncio
async def test_update_api_failure_passes_error_and_error_code(
    discovery_client: TestClient,
) -> None:
    """update 失败时透传 error/error_code，且不触发 audit。"""
    failed_result = SkillInstallResult(
        success=False,
        skill_name="demo-skill",
        skill_id="demo-skill",
        installed_path="",
        error="Download failed.",
        error_code="",
    )
    with (
        patch(
            "app.core.skills.discovery.autoupdate.SkillAutoUpdateChecker.update_skill",
            new=AsyncMock(return_value=failed_result),
        ),
        patch("app.api.skills.discovery._audit_skill_action") as audit,
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new=AsyncMock(),
        ),
        patch(
            "app.services.agent.agent_service.AgentService.update_agent",
            new=AsyncMock(),
        ),
    ):
        response = discovery_client.post(
            "/api/v1/skills/discovery/update",
            json={
                "skill_name": "demo-skill",
                "skill_id": "demo-skill",
                "source": "clawhub",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == failed_result.error
    assert body["error_code"] == ""
    assert body["mounted"] is False
    audit.assert_not_called()


@pytest.mark.asyncio
async def test_install_appends_explicit_allowlist_when_agent_has_subset(
    discovery_client: TestClient,
) -> None:
    prebuilt_id = "systematic-debugging"
    install_result = SkillInstallResult(
        success=True,
        skill_name="Systematic Debugging",
        skill_id=prebuilt_id,
        installed_path="prebuilt (already installed)",
    )
    agent = type("Agent", (), {"skills": ["code-review"]})()
    update_agent = AsyncMock(return_value=agent)

    with (
        patch.object(
            market_service._base,
            "install",
            new=AsyncMock(return_value=install_result),
        ),
        patch(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            new=AsyncMock(),
        ),
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new=AsyncMock(return_value=agent),
        ),
        patch(
            "app.services.agent.agent_service.AgentService.update_agent",
            new=update_agent,
        ),
        patch("app.api.skills.discovery._audit_skill_action"),
    ):
        response = discovery_client.post(
            "/api/v1/skills/discovery/install",
            json={
                "skill_id": prebuilt_id,
                "source": "prebuilt",
                "mount_to_agent": True,
                "agent_id": "builtin-general",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["mounted"] is True
    assert body["allowlist_appended"] is True
    update_agent.assert_awaited_once()
    merged = update_agent.await_args.args[1].skill_ids
    assert merged == ["code-review", prebuilt_id]


@pytest.mark.asyncio
async def test_install_reports_allowlist_append_error_when_update_fails(
    discovery_client: TestClient,
) -> None:
    prebuilt_id = "systematic-debugging"
    install_result = SkillInstallResult(
        success=True,
        skill_name="Systematic Debugging",
        skill_id=prebuilt_id,
        installed_path="prebuilt (already installed)",
    )
    agent = type("Agent", (), {"skills": ["code-review"]})()

    with (
        patch.object(
            market_service._base,
            "install",
            new=AsyncMock(return_value=install_result),
        ),
        patch(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            new=AsyncMock(),
        ),
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            new=AsyncMock(return_value=agent),
        ),
        patch(
            "app.services.agent.agent_service.AgentService.update_agent",
            new=AsyncMock(return_value=None),
        ),
        patch("app.api.skills.discovery._audit_skill_action"),
    ):
        response = discovery_client.post(
            "/api/v1/skills/discovery/install",
            json={
                "skill_id": prebuilt_id,
                "source": "prebuilt",
                "mount_to_agent": True,
                "agent_id": "builtin-general",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["mounted"] is True
    assert body["allowlist_appended"] is False
    assert body["allowlist_append_error"]
