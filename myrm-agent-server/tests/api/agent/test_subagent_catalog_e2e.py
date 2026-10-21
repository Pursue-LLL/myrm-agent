"""端到端集成测试：SubagentCatalog + CustomAgentFactory

测试 DatabaseSubagentCatalog 的完整生命周期：
1. YAML preset 解析 + ModelResolver 注入
2. DB custom agent 解析 + CustomAgentFactory 注入
3. list_available 返回 YAML + DB agents
4. Bound agent_ids 过滤

测试 CustomAgentFactory.build() 的资源初始化缓存行为
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.sub_agents.types import ControlScope, MemoryIsolationPolicy, SubagentConfig


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def test_user_id():
    return "test-user-id"


async def _create_test_agent(client: AsyncClient, name: str, **overrides) -> dict:
    payload = {
        "name": name,
        "description": f"Test agent: {name}",
        "system_prompt": f"You are {name}.",
        "is_built_in": False,
        **overrides,
    }
    response = await client.post("/api/agents", json=payload)
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.asyncio
class TestDatabaseSubagentCatalog:
    async def test_resolve_yaml_preset(self, test_user_id: str):
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        catalog = DatabaseSubagentCatalog()
        yaml_ids = [k for k in catalog._yaml_configs]

        if not yaml_ids:
            pytest.skip("No YAML subagent presets configured")

        first_id = yaml_ids[0]
        config = await catalog.resolve(first_id)
        assert config is not None
        assert isinstance(config, SubagentConfig)
        assert config.system_prompt

    async def test_resolve_yaml_injects_model_resolver(self, test_user_id: str):
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        catalog = DatabaseSubagentCatalog()

        for type_id, cfg in catalog._yaml_configs.items():
            if cfg.model and cfg.model_resolver is None:
                resolved = await catalog.resolve(type_id)
                assert resolved is not None
                assert resolved.model_resolver is not None
                return

        pytest.skip("No YAML preset with model field found")

    async def test_resolve_db_agent(self, async_client: AsyncClient, test_user_id: str):
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        agent = await _create_test_agent(
            async_client,
            "SubagentCatalogTest",
            system_prompt="I am a test subagent",
            skill_ids=["search"],
        )
        agent_id = agent["id"]

        catalog = DatabaseSubagentCatalog()
        config = await catalog.resolve(agent_id)

        assert config is not None
        assert isinstance(config, SubagentConfig)
        assert config.system_prompt == "I am a test subagent"
        assert config.display_name == "SubagentCatalogTest"
        assert config.control_scope == ControlScope.LEAF
        assert config.memory_isolation == MemoryIsolationPolicy.READ_ONLY_GLOBAL
        assert config.max_spawn_depth == 0
        assert config.agent_factory is not None

    async def test_resolve_nonexistent_returns_none(self, test_user_id: str):
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        catalog = DatabaseSubagentCatalog()
        config = await catalog.resolve("nonexistent-agent-id-99999")
        assert config is None

    async def test_bound_agent_ids_filter(self, async_client: AsyncClient, test_user_id: str):
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        agent_a = await _create_test_agent(async_client, "Agent A")
        agent_b = await _create_test_agent(async_client, "Agent B")

        catalog = DatabaseSubagentCatalog(
            bound_agent_ids=[agent_a["id"]],
        )

        config_a = await catalog.resolve(agent_a["id"])
        assert config_a is not None

        config_b = await catalog.resolve(agent_b["id"])
        assert config_b is None

    async def test_list_available_includes_yaml_and_db(self, async_client: AsyncClient, test_user_id: str):
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        await _create_test_agent(async_client, "ListTest Agent")

        catalog = DatabaseSubagentCatalog()
        available = await catalog.list_available()

        assert isinstance(available, list)
        yaml_count = len(catalog._yaml_configs)
        assert len(available) >= yaml_count

    async def test_list_available_with_bound_ids(self, async_client: AsyncClient, test_user_id: str):
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        agent = await _create_test_agent(async_client, "BoundList Agent")
        agent_id = agent["id"]

        catalog = DatabaseSubagentCatalog(
            bound_agent_ids=[agent_id],
        )
        available = await catalog.list_available()

        yaml_count = len(catalog._yaml_configs)
        assert len(available) == yaml_count + 1
        assert agent_id in available


@pytest.mark.asyncio
class TestCustomAgentFactory:
    async def test_factory_initialization_caching(self, async_client: AsyncClient, test_user_id: str):
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        agent = await _create_test_agent(
            async_client,
            "CacheTest Agent",
            skill_ids=["search"],
        )
        agent_id = agent["id"]

        catalog = DatabaseSubagentCatalog()
        config = await catalog.resolve(agent_id)
        assert config is not None

        factory = config.agent_factory
        assert factory is not None
        assert not factory._initialized

        await factory._ensure_initialized()
        assert factory._initialized

        first_backend = factory._cached_skill_backend

        await factory._ensure_initialized()
        assert factory._cached_skill_backend is first_backend

    async def test_factory_display_name_propagation(self, async_client: AsyncClient, test_user_id: str):
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        agent = await _create_test_agent(
            async_client,
            "显示名称测试",
            description="Test display name propagation",
        )
        agent_id = agent["id"]

        catalog = DatabaseSubagentCatalog()
        config = await catalog.resolve(agent_id)

        assert config is not None
        assert config.display_name == "显示名称测试"

    async def test_factory_max_turns_from_profile(self, async_client: AsyncClient, test_user_id: str):
        from app.ai_agents.subagent_catalog import DatabaseSubagentCatalog

        agent = await _create_test_agent(
            async_client,
            "MaxTurns Agent",
            max_iterations=50,
        )
        agent_id = agent["id"]

        catalog = DatabaseSubagentCatalog()
        config = await catalog.resolve(agent_id)

        assert config is not None
        assert config.max_turns == 50


@pytest.mark.asyncio
class TestLLMModelResolver:
    @pytest.mark.skipif(
        not os.environ.get("BASIC_API_KEY"),
        reason="Requires BASIC_API_KEY for real model resolution",
    )
    async def test_resolve_real_model(self):
        from app.ai_agents.subagent_catalog import _LLMModelResolver

        resolver = _LLMModelResolver()
        model_name = os.getenv("BASIC_MODEL")
        if not model_name:
            raise RuntimeError("BASIC_MODEL must be set")

        llm = await resolver.resolve(model_name)
        assert llm is not None

    async def test_resolver_propagates_errors(self):
        """_LLMModelResolver.resolve propagates exceptions (fail-fast behavior).

        The harness builder.py catches these in resolve_llm and falls back to parent.
        """
        from unittest.mock import patch

        from app.ai_agents.subagent_catalog import _LLMModelResolver

        resolver = _LLMModelResolver()

        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            side_effect=RuntimeError("config load failed"),
        ):
            with pytest.raises(RuntimeError, match="config load failed"):
                await resolver.resolve("nonexistent/model")
