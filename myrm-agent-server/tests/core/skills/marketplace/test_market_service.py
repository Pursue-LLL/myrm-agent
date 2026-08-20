from types import SimpleNamespace
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
                _make_response(200, "---\nname: skill1\ndescription: The first skill\n---\n"),
                _make_response(200, "---\nname: skill2\ndescription: The second skill\n---\n"),
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
        patch.object(service, "_auto_disable_local_skill", new_callable=AsyncMock) as mock_disable,
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
        patch.object(service, "_auto_disable_local_skill", new_callable=AsyncMock) as mock_disable,
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


@pytest.mark.asyncio
async def test_install_forwards_without_progress_callback() -> None:
    """install 必须转发到底层 _base，且不再传递 progress_callback（SSE 死代码删除后契约）。"""
    service = SkillMarketService()
    result = MagicMock(success=True)
    with patch.object(service, "_base") as mock_base:
        mock_base.install = AsyncMock(return_value=result)
        res = await service.install("skill-1", "github")

    assert res is result
    mock_base.install.assert_awaited_once_with("skill-1", "github")
    # 不得把 progress_callback 作为额外 kwargs 传给底层（删除 SSE 进度发布后不再透传）。
    call_kwargs = mock_base.install.await_args.kwargs
    assert "progress_callback" not in call_kwargs


@pytest.mark.asyncio
async def test_install_from_url_forwards_without_progress_callback() -> None:
    """install_from_url 必须转发到底层 _base，且不再传递 progress_callback。"""
    service = SkillMarketService()
    result = MagicMock(success=True)
    with patch.object(service, "_base") as mock_base:
        mock_base.install_from_url = AsyncMock(return_value=result)
        res = await service.install_from_url("https://github.com/test/repo")

    assert res is result
    mock_base.install_from_url.assert_awaited_once_with("https://github.com/test/repo")
    call_kwargs = mock_base.install_from_url.await_args.kwargs
    assert "progress_callback" not in call_kwargs


@pytest.mark.asyncio
async def test_search_forwards_installed_versions() -> None:
    """search 必须把本地已安装版本映射传给底层 _base.search。"""
    service = SkillMarketService()
    with patch.object(service, "_base") as mock_base:
        mock_base.search = AsyncMock(return_value=[MagicMock()])
        res = await service.search("query", limit=10)

    assert len(res) == 1
    mock_base.search.assert_awaited_once()
    _, kwargs = mock_base.search.await_args
    assert kwargs["limit"] == 10
    assert "installed_versions_map" in kwargs


@pytest.mark.asyncio
async def test_get_installed_versions_returns_map() -> None:
    """_get_installed_versions 返回 name→version 映射（内部用于搜索 enrich）。"""
    service = SkillMarketService()
    with patch(
        "app.core.skills.store.service.skills_service.list_skills",
        new_callable=AsyncMock,
    ) as mock_list:
        s1 = MagicMock()
        s1.name = "SkillA"
        s1.version = "1.0.0"
        s2 = MagicMock()
        s2.name = "skill-b"
        s2.version = "2.1.0"
        mock_list.return_value = [s1, s2]
        versions = await service._get_installed_versions()

    assert versions == {"skilla": "1.0.0", "skill-b": "2.1.0"}


@pytest.mark.asyncio
async def test_get_installed_versions_failure_returns_empty() -> None:
    """获取已安装版本失败时返回空 dict（避免阻塞搜索流程）。"""
    service = SkillMarketService()
    with patch(
        "app.core.skills.store.service.skills_service.list_skills",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db down"),
    ):
        versions = await service._get_installed_versions()

    assert versions == {}


@pytest.mark.asyncio
async def test_get_installed_local_ids_by_name() -> None:
    """get_installed_local_ids_by_name 只返回 local:: 前缀技能。"""
    service = SkillMarketService()
    with patch(
        "app.core.skills.store.service.skills_service.list_skills",
        new_callable=AsyncMock,
    ) as mock_list:
        s1 = MagicMock()
        s1.name = "MySkill"
        s1.id = "local::abc"
        s2 = MagicMock()
        s2.name = "Prebuilt"
        s2.id = "prebuilt::def"
        mock_list.return_value = [s1, s2]
        mapping = await service.get_installed_local_ids_by_name()

    assert mapping == {"myskill": "local::abc"}


def test_refresh_clawhub_source_clears_cache() -> None:
    """refresh_clawhub_source 必须重置 clawhub 源客户端并清空搜索缓存。"""
    service = SkillMarketService()
    reset = MagicMock()
    clawhub = MagicMock(source_name="clawhub", reset_client=reset)
    other = MagicMock(source_name="github", reset_client=MagicMock())
    with patch.object(service, "_base") as mock_base:
        mock_base._sources = [clawhub, other]
        mock_base._search_cache = {"k": (1.0, [])}
        service.refresh_clawhub_source()

    reset.assert_called_once()
    assert mock_base._search_cache == {}


def test_sources_property() -> None:
    """_sources property 透传底层 discovery sources。"""
    service = SkillMarketService()
    with patch.object(service, "_base") as mock_base:
        mock_base._sources = [MagicMock(), MagicMock()]
        assert service._sources == mock_base._sources


@pytest.mark.asyncio
async def test_analyze_url_error_returns_empty_list(mock_analyze_github_url) -> None:
    """analyze_url 遇到异常（如 GitHub API 失败）必须返回空列表而非抛错。"""
    service = SkillMarketService()
    mock_analyze_github_url.side_effect = ValueError("repo not found")
    with patch(
        "app.core.skills.store.service.skills_service.list_skills",
        new_callable=AsyncMock,
        return_value=[],
    ):
        results = await service.analyze_url("https://github.com/owner/missing")

    assert results == []


@pytest.mark.asyncio
async def test_analyze_url_fetch_metadata_error_keeps_working(
    mock_analyze_github_url,
) -> None:
    """单个子目录 metadata 拉取失败不得中断整个 analyze（降级为默认 name/description）。"""
    service = SkillMarketService()
    mock_analyze_github_url.return_value = [
        SimpleNamespace(owner="o", repo="r", ref="main", subdirectory="skills/a"),
    ]
    with (
        patch(
            "app.core.skills.store.service.skills_service.list_skills",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("httpx.AsyncClient") as mock_client,
    ):
        client_instance = mock_client.return_value
        client_instance.__aenter__.return_value = client_instance
        client_instance.get.side_effect = RuntimeError("network down")
        results = await service.analyze_url("https://github.com/o/r")

    assert len(results) == 1
    assert results[0]["name"] == "a"


@pytest.mark.asyncio
async def test_ensure_clawhub_registry_applies_config() -> None:
    """ensure_clawhub_registry 首次调用必须 apply registry URL（含 legacy 迁移），幂等。"""
    service = SkillMarketService()
    assert service._clawhub_registry_applied is False

    class FakeConfig:
        clawhub_registry_url = "https://legacy.skillhub.cn"

    async def fake_get_config():
        return FakeConfig()

    async def fake_update_config(**kwargs):
        return None

    with (
        patch(
            "app.core.skills.store.service.skills_service.user_config.get_config",
            new_callable=lambda: AsyncMock(side_effect=fake_get_config),
        ),
        patch(
            "app.core.skills.store.service.skills_service.user_config.update_config",
            new_callable=lambda: AsyncMock(side_effect=fake_update_config),
        ),
        patch(
            "myrm_agent_harness.agent.skills.market.sources.clawhub_registry.migrate_legacy_registry_url",
            side_effect=lambda u: u,
        ) as mock_migrate,
        patch(
            "app.core.skills.marketplace.clawhub_registry.normalize_clawhub_registry_url",
            side_effect=lambda u: u,
        ),
        patch(
            "app.core.skills.marketplace.clawhub_registry.apply_clawhub_registry_url",
        ) as mock_apply,
    ):
        await service.ensure_clawhub_registry()
        await service.ensure_clawhub_registry()  # 幂等：第二次不再 apply

    mock_migrate.assert_called_once()
    mock_apply.assert_called_once()
    assert service._clawhub_registry_applied is True


def test_register_custom_sources_invalid_entry_warns() -> None:
    """无效的 well-known 自定义源必须被跳过并告警，不得中断注册。"""
    service = SkillMarketService()
    with (
        patch(
            "app.core.skills.marketplace.custom_source_config.load_custom_sources",
        ) as mock_load,
        patch(
            "myrm_agent_harness.agent.skills.market.sources.wellknown.WellKnownSkillSource",
            side_effect=ValueError("bad url"),
        ) as mock_wellknown,
    ):
        mock_load.return_value = SimpleNamespace(sources=[SimpleNamespace(source_type="well-known", url="http://bad")])
        with patch.object(service, "_base") as mock_base:
            service._register_custom_sources()

    mock_wellknown.assert_called_once()
    mock_base.register_source.assert_not_called()


@pytest.mark.asyncio
async def test_uninstall_purge_failure_keeps_result() -> None:
    """卸载成功但权限清理失败时必须保留卸载结果（降级为 warning）。"""
    service = SkillMarketService()
    result = MagicMock(success=True)
    with (
        patch.object(service, "_base") as mock_base,
        patch.object(service, "_auto_disable_local_skill", new_callable=AsyncMock),
        patch(
            "app.core.skills.marketplace.market_service.purge_skill_permissions",
            new_callable=AsyncMock,
            side_effect=RuntimeError("purge db down"),
        ),
    ):
        mock_base.uninstall = AsyncMock(return_value=result)
        res = await service.uninstall("skill-1")

    assert res is result


@pytest.mark.asyncio
async def test_auto_disable_local_skill_removes_from_config() -> None:
    """卸载后 _auto_disable_local_skill 必须把技能从 enabled_local_skill_ids 移除并保存。"""
    service = SkillMarketService()

    class FakeConfig:
        def __init__(self):
            self.enabled_local_skill_ids = ["local::abc", "other"]

    config = FakeConfig()

    with (
        patch(
            "app.core.skills.store.service.skills_service.user_config.get_config",
            new_callable=AsyncMock,
            return_value=config,
        ),
        patch(
            "app.core.skills.store.service.skills_service.user_config.save_config",
            new_callable=AsyncMock,
        ) as mock_save,
    ):
        await service._auto_disable_local_skill("local::abc")

    assert config.enabled_local_skill_ids == ["other"]
    mock_save.assert_awaited_once_with(config)


@pytest.mark.asyncio
async def test_app_skill_store_list_installed() -> None:
    """_AppSkillStore.list_installed 适配业务技能为 InstalledSkillInfo 列表。"""
    from app.core.skills.marketplace.market_service import _AppSkillStore

    store = _AppSkillStore()
    skill = MagicMock()
    skill.id = "local::abc"
    skill.name = "MySkill"
    skill.description = "desc"
    skill.version = "1.2.3"
    skill.tags = ["tag1"]
    with patch(
        "app.core.skills.store.service.skills_service.list_skills",
        new_callable=AsyncMock,
        return_value=[skill],
    ):
        installed = await store.list_installed()

    assert len(installed) == 1
    assert installed[0].id == "local::abc"
    assert installed[0].version == "1.2.3"


@pytest.mark.asyncio
async def test_app_skill_store_get_installed() -> None:
    """_AppSkillStore.get_installed 命中返回信息，未命中返回 None。"""
    from app.core.skills.marketplace.market_service import _AppSkillStore

    store = _AppSkillStore()
    with patch(
        "app.core.skills.store.service.skills_service.get_skill",
        new_callable=AsyncMock,
        return_value=None,
    ):
        assert await store.get_installed("local::abc") is None

    skill = MagicMock()
    skill.id = "local::abc"
    skill.name = "MySkill"
    skill.description = "desc"
    skill.version = "1.2.3"
    skill.tags = ["tag1"]
    with patch(
        "app.core.skills.store.service.skills_service.get_skill",
        new_callable=AsyncMock,
        return_value=skill,
    ):
        installed = await store.get_installed("local::abc")

    assert installed is not None
    assert installed.name == "MySkill"


@pytest.mark.asyncio
async def test_market_service_agent_plugin_search_and_install() -> None:
    """SkillMarketService correctly handles Agent Plugin search and install flows."""
    from myrm_agent_harness.agent.skills.market.service import EnrichedSearchResult
    from myrm_agent_harness.backends.skills.market_protocols import (
        SkillInstallResult,
        SkillSearchResult,
    )

    service = SkillMarketService()

    plugin_res = EnrichedSearchResult(
        result=SkillSearchResult(
            id="plugin::doc-tools",
            name="doc-tools",
            description="Doc tooling agent plugin",
            source="github",
            author="myrm",
            install_url="https://github.com/myrm/doc-tools.git",
            install_method="git",
            version="1.0.0",
            package_type="agent_plugin",
            keywords=["doc", "markdown"],
        )
    )

    with (
        patch.object(service._base, "search", new_callable=AsyncMock) as mock_search,
        patch.object(service._base, "install", new_callable=AsyncMock) as mock_install,
    ):
        mock_search.return_value = [plugin_res]
        mock_install.return_value = SkillInstallResult(
            success=True,
            skill_name="doc-tools",
            skill_id="local::doc-tools",
            installed_path="/tmp/skills/doc-tools",
            installed_skills=["doc-gen", "doc-lint"],
        )

        # 1. Search
        search_results = await service.search("doc")
        assert len(search_results) == 1
        assert search_results[0].result.package_type == "agent_plugin"
        assert search_results[0].result.keywords == ["doc", "markdown"]

        # 2. Install
        install_res = await service.install("plugin::doc-tools", "github")
        assert install_res.success is True
        assert install_res.installed_skills == ["doc-gen", "doc-lint"]
