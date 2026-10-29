"""Skill market install: a download the install step refuses is an install failure, not an exception.

[INPUT]
- myrm_agent_harness.agent.skills.market.service::BaseSkillMarketService

[OUTPUT]
- `install` and `install_from_url` return `success=False` with the reason when the downloaded files are over the size
  limits or all fall in filtered paths, on the git and the ZIP path alike

[POS]
myrm-agent-harness/tests/agent/skills/market/test_service_install_limits.py
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.skills.market.installers.base import InstalledSkillFiles
from myrm_agent_harness.agent.skills.market.sanitizer import MAX_SINGLE_FILE_SIZE, MAX_TOTAL_UPLOAD_SIZE
from myrm_agent_harness.agent.skills.market.service import BaseSkillMarketService
from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult, SkillSearchResult

SKILL_MD = b"---\nname: Alpha\ndescription: d\n---\n# Alpha\n"


def _detail(install_method: str) -> SkillSearchResult:
    return SkillSearchResult(
        id="repo:alpha",
        name="Alpha",
        description="d",
        source="repo",
        author="a",
        install_url="https://example.invalid",
        install_method=install_method,  # type: ignore[arg-type]
    )


def _downloaded(files: dict[str, bytes]) -> InstalledSkillFiles:
    return InstalledSkillFiles(name="Alpha", description="d", files=files)


@pytest.fixture
def service() -> BaseSkillMarketService:
    return BaseSkillMarketService()


async def _install(service: BaseSkillMarketService, install_method: str, files: dict[str, bytes]) -> SkillInstallResult:
    installer = service._git_installer if install_method == "git" else service._zip_installer
    with (
        patch.object(BaseSkillMarketService, "get_detail", return_value=_detail(install_method)),
        patch.object(type(installer), "download", new=AsyncMock(return_value=_downloaded(files))),
    ):
        return await service.install("repo:alpha", "repo")


@pytest.mark.asyncio
@pytest.mark.parametrize("install_method", ["git", "zip"])
async def test_a_file_over_the_single_file_limit_fails_the_install(
    service: BaseSkillMarketService, install_method: str
) -> None:
    result = await _install(
        service, install_method, {"SKILL.md": SKILL_MD, "big.bin": b"\0" * (MAX_SINGLE_FILE_SIZE + 1)}
    )

    assert result.success is False
    assert "exceeds size limit" in (result.error or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("install_method", ["git", "zip"])
async def test_a_skill_over_the_total_limit_fails_the_install(
    service: BaseSkillMarketService, install_method: str
) -> None:
    parts = {f"part{i}.bin": b"\0" * 900_000 for i in range(MAX_TOTAL_UPLOAD_SIZE // 900_000 + 1)}

    result = await _install(service, install_method, {"SKILL.md": SKILL_MD, **parts})

    assert result.success is False
    assert "Total upload size exceeds limit" in (result.error or "")


@pytest.mark.asyncio
async def test_a_skill_whose_files_are_all_filtered_fails_the_install(service: BaseSkillMarketService) -> None:
    result = await _install(service, "git", {"dist/SKILL.md": SKILL_MD})

    assert result.success is False
    assert "No valid files" in (result.error or "")


@pytest.mark.asyncio
async def test_install_from_url_fails_instead_of_raising_over_the_size_limit(service: BaseSkillMarketService) -> None:
    files = {"SKILL.md": SKILL_MD, "big.bin": b"\0" * (MAX_SINGLE_FILE_SIZE + 1)}

    with patch.object(type(service._git_installer), "download", new=AsyncMock(return_value=_downloaded(files))):
        result = await service.install_from_url("https://github.com/owner/repo")

    assert result.success is False
    assert "exceeds size limit" in (result.error or "")
