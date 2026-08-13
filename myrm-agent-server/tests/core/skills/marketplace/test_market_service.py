from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.skills.marketplace.market_service import SkillMarketService


def _make_response(status_code: int, text: str = "") -> MagicMock:
    """Create a sync MagicMock that mimics httpx.Response (text is a property, not coroutine)."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


@pytest.fixture
def mock_analyze_github_url():
    with patch(
        "app.core.skills.marketplace.market_service.analyze_github_url",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.mark.asyncio
async def test_analyze_url_success(mock_analyze_github_url):
    service = SkillMarketService()

    class MockRef:
        def __init__(self, owner, repo, ref, subdirectory):
            self.owner = owner
            self.repo = repo
            self.ref = ref
            self.subdirectory = subdirectory

    mock_analyze_github_url.return_value = [
        MockRef("owner", "repo", "main", "skills/skill1"),
        MockRef("owner", "repo", "main", "skills/skill2"),
    ]

    url = "https://github.com/owner/repo"
    with (
        patch(
            "app.core.skills.store.service.skills_service.list_skills",
            new_callable=AsyncMock,
        ) as mock_list_skills,
        patch("httpx.AsyncClient") as mock_client,
    ):

        class MockSkill:
            name = "skill1"
            version = "1.0.0"

        mock_list_skills.return_value = [MockSkill()]

        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        mock_instance.get = AsyncMock(
            side_effect=[
                _make_response(
                    200, "---\nname: skill1\ndescription: The first skill\n---\n"
                ),
                _make_response(
                    200, "---\nname: skill2\ndescription: The second skill\n---\n"
                ),
            ]
        )
        results = await service.analyze_url(url)

    assert len(results) == 2
    assert results[0]["url"] == "https://github.com/owner/repo/tree/main/skills/skill1"
    assert results[0]["name"] == "skill1"
    assert "description" in results[0]
    assert results[0]["is_installed"] is True
    assert results[1]["url"] == "https://github.com/owner/repo/tree/main/skills/skill2"
    assert results[1]["name"] == "skill2"
    assert "description" in results[1]
    assert results[1]["is_installed"] is False


@pytest.mark.asyncio
async def test_analyze_url_fallback(mock_analyze_github_url):
    service = SkillMarketService()

    mock_analyze_github_url.side_effect = Exception("Rate limit")

    url = "https://github.com/owner/repo"
    results = await service.analyze_url(url)

    assert results == []


@pytest.mark.asyncio
async def test_analyze_url_no_subdirectory(mock_analyze_github_url):
    service = SkillMarketService()

    class MockRef:
        def __init__(self, owner, repo, ref, subdirectory):
            self.owner = owner
            self.repo = repo
            self.ref = ref
            self.subdirectory = subdirectory

    mock_analyze_github_url.return_value = [
        MockRef("owner", "repo", "main", None),
    ]

    url = "https://github.com/owner/repo"
    with (
        patch(
            "app.core.skills.store.service.skills_service.list_skills",
            new_callable=AsyncMock,
        ) as mock_list_skills,
        patch("httpx.AsyncClient") as mock_client,
    ):
        mock_list_skills.return_value = []

        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        mock_instance.get = AsyncMock(return_value=_make_response(404))

        results = await service.analyze_url(url)

    assert len(results) == 1
    assert results[0]["url"] == "https://github.com/owner/repo"
    assert results[0]["name"] == "repo"
    assert "description" in results[0]
    assert results[0]["is_installed"] is False


@pytest.mark.asyncio
async def test_uninstall_success_purges_permission_data() -> None:
    """卸载成功时必须同步清理该技能的授权/审计数据与缓存。"""
    service = SkillMarketService()
    result = MagicMock(success=True)
    with (
        patch.object(service, "_base") as mock_base,
        patch.object(
            service, "_auto_disable_local_skill", new_callable=AsyncMock
        ) as mock_disable,
        patch(
            "app.core.skills.marketplace.market_service.purge_skill_permissions",
            new_callable=AsyncMock,
        ) as mock_purge,
    ):
        mock_base.uninstall = AsyncMock(return_value=result)
        res = await service.uninstall("skill-1")

    assert res is result
    mock_disable.assert_awaited_once_with("skill-1")
    mock_purge.assert_awaited_once_with("skill-1")


@pytest.mark.asyncio
async def test_uninstall_failure_skips_purge() -> None:
    """卸载失败时不得清理权限数据（避免误删仍在使用的授权）。"""
    service = SkillMarketService()
    result = MagicMock(success=False)
    with (
        patch.object(service, "_base") as mock_base,
        patch.object(
            service, "_auto_disable_local_skill", new_callable=AsyncMock
        ) as mock_disable,
        patch(
            "app.core.skills.marketplace.market_service.purge_skill_permissions",
            new_callable=AsyncMock,
        ) as mock_purge,
    ):
        mock_base.uninstall = AsyncMock(return_value=result)
        res = await service.uninstall("skill-1")

    assert res is result
    mock_disable.assert_not_awaited()
    mock_purge.assert_not_awaited()
