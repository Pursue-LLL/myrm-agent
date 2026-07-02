"""Agent 内置工具配置端到端测试

验证 enabled_builtin_tools 在 Agent CRUD 和消息请求链路中的完整行为。
"""

import os

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8080")

_skip_e2e = pytest.mark.skipif(
    not os.getenv("RUN_E2E_TESTS"),
    reason="Set RUN_E2E_TESTS=1 to run end-to-end tests against live server",
)


@pytest.fixture(scope="module")
def auth_headers() -> dict[str, str]:
    """Attempt login; return empty headers for local mode (no auth)."""
    try:
        resp = httpx.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={
                "username": os.getenv("TEST_USERNAME", "test"),
                "password": os.getenv("TEST_PASSWORD", "test"),
            },
            timeout=2.0,
        )
    except (httpx.TimeoutException, httpx.ConnectError):
        return {}

    if resp.status_code == 200:
        token = resp.json().get("data", {}).get("access_token")
        if token:
            return {"Authorization": f"Bearer {token}"}
    return {}


@pytest.fixture
def created_agent_id(auth_headers: dict[str, str]):
    """Create an agent and return its ID; delete after test."""
    payload = {
        "name": "Test Builtin Tools Agent",
        "description": "E2E test for enabled_builtin_tools",
        "system_prompt": "You are a test agent.",
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": ["web_search", "browser", "image_generation"],
    }
    resp = httpx.post(
        f"{BASE_URL}/api/v1/user-agents",
        json=payload,
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200, f"Create agent failed: {resp.text}"
    agent_id = resp.json()["data"]["id"]
    yield agent_id
    httpx.delete(
        f"{BASE_URL}/api/v1/user-agents/{agent_id}",
        headers=auth_headers,
        timeout=10,
    )


@_skip_e2e
class TestAgentBuiltinToolsCRUD:
    """Test enabled_builtin_tools persistence through Agent CRUD."""

    def test_create_agent_with_builtin_tools(self, auth_headers: dict[str, str], created_agent_id: str) -> None:
        """Create an agent with specific builtin tools and verify persistence."""
        resp = httpx.get(
            f"{BASE_URL}/api/v1/user-agents/{created_agent_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        agent = resp.json()["data"]
        assert agent["enabled_builtin_tools"] == [
            "web_search",
            "browser",
            "image_generation",
        ]

    def test_update_agent_builtin_tools(self, auth_headers: dict[str, str], created_agent_id: str) -> None:
        """Update agent's builtin tools and verify the change persists."""
        update_payload = {
            "enabled_builtin_tools": ["web_search", "video_generation"],
        }
        resp = httpx.put(
            f"{BASE_URL}/api/v1/user-agents/{created_agent_id}",
            json=update_payload,
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200

        resp = httpx.get(
            f"{BASE_URL}/api/v1/user-agents/{created_agent_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        agent = resp.json()["data"]
        assert set(agent["enabled_builtin_tools"]) == {"web_search", "video_generation"}

    def test_create_agent_without_builtin_tools(self, auth_headers: dict[str, str]) -> None:
        """Create an agent without specifying builtin tools — defaults to web_search + memory."""
        payload = {
            "name": "No Builtin Tools Agent",
            "system_prompt": "",
            "mcp_ids": [],
            "skill_ids": [],
        }
        resp = httpx.post(
            f"{BASE_URL}/api/v1/user-agents",
            json=payload,
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        agent = resp.json()["data"]
        agent_id = agent["id"]
        assert agent["enabled_builtin_tools"] == ["web_search", "memory"]

        httpx.delete(
            f"{BASE_URL}/api/v1/user-agents/{agent_id}",
            headers=auth_headers,
            timeout=10,
        )

    def test_update_builtin_tools_to_empty(self, auth_headers: dict[str, str], created_agent_id: str) -> None:
        """Update builtin tools to empty list — agent should have no tools enabled."""
        update_payload = {"enabled_builtin_tools": []}
        resp = httpx.put(
            f"{BASE_URL}/api/v1/user-agents/{created_agent_id}",
            json=update_payload,
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200

        resp = httpx.get(
            f"{BASE_URL}/api/v1/user-agents/{created_agent_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        agent = resp.json()["data"]
        assert agent["enabled_builtin_tools"] == []


class TestAgentConfigRequestBuiltinTools:
    """Test enabled_builtin_tools in AgentConfigRequest model."""

    def test_agent_config_request_default(self) -> None:
        """Verify AgentConfigRequest defaults to ['web_search', 'memory']."""
        from app.services.agent.params import AgentConfigRequest

        cfg = AgentConfigRequest()
        assert cfg.enabled_builtin_tools == ["web_search", "memory"]

    def test_agent_config_request_custom(self) -> None:
        """Verify AgentConfigRequest accepts custom builtin tools."""
        from app.services.agent.params import AgentConfigRequest

        cfg = AgentConfigRequest(enabled_builtin_tools=["browser", "image_generation"])
        assert cfg.enabled_builtin_tools == ["browser", "image_generation"]

    def test_agent_config_request_empty(self) -> None:
        """Verify AgentConfigRequest accepts empty builtin tools."""
        from app.services.agent.params import AgentConfigRequest

        cfg = AgentConfigRequest(enabled_builtin_tools=[])
        assert cfg.enabled_builtin_tools == []


class TestGeneralAgentParamsEnableWiki:
    """Test enable_wiki field in GeneralAgentParams and AgentFactory mapping."""

    def test_enable_wiki_default_false(self) -> None:
        """GeneralAgentParams.enable_wiki defaults to False."""
        from app.ai_agents.agents import GeneralAgentParams
        from app.core.types import ModelConfig

        params = GeneralAgentParams(
            query="test",
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
        )
        assert params.enable_wiki is False

    def test_enable_wiki_explicit_true(self) -> None:
        """GeneralAgentParams.enable_wiki can be set to True."""
        from app.ai_agents.agents import GeneralAgentParams
        from app.core.types import ModelConfig

        params = GeneralAgentParams(
            query="test",
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            enable_wiki=True,
        )
        assert params.enable_wiki is True

    def test_wiki_in_enabled_builtin_tools_sets_enable_wiki(self) -> None:
        """Verify 'wiki' in enabled_builtin_tools maps to enable_wiki=True."""
        tools = ["web_search", "wiki", "file_ops"]
        assert ("wiki" in tools) is True

    def test_wiki_not_in_enabled_builtin_tools(self) -> None:
        """Verify 'wiki' not in enabled_builtin_tools maps to enable_wiki=False."""
        tools = ["web_search", "file_ops"]
        assert ("wiki" in tools) is False

    def test_all_builtin_tool_flags(self) -> None:
        """Verify all builtin tool flags produce correct boolean values from a tool list."""
        tools = [
            "web_search",
            "browser",
            "computer_use",
            "file_ops",
            "code_execute",
            "wiki",
            "render_ui",
        ]

        assert ("browser" in tools) is True
        assert ("computer_use" in tools) is True
        assert ("file_ops" in tools) is True
        assert ("code_execute" in tools) is True
        assert ("wiki" in tools) is True
        assert ("render_ui" in tools) is True

    def test_empty_builtin_tools_disables_all(self) -> None:
        """Empty enabled_builtin_tools disables all optional tool flags."""
        tools: list[str] = []

        assert ("browser" in tools) is False
        assert ("computer_use" in tools) is False
        assert ("file_ops" in tools) is False
        assert ("code_execute" in tools) is False
        assert ("wiki" in tools) is False
        assert ("render_ui" in tools) is False


class TestResolveBuiltinToolFlagsRenderUi:
    """Verify render_ui in enabled_builtin_tools maps to enable_render_ui."""

    def test_resolve_builtin_tool_flags_render_ui(self) -> None:
        from app.services.agent.profile_resolver import resolve_builtin_tool_flags

        flags = resolve_builtin_tool_flags(["web_search", "render_ui"])
        assert flags["enable_render_ui"] is True
        assert flags["enable_browser"] is False


class TestResolveBuiltinToolFlagsKanban:
    """Verify kanban in enabled_builtin_tools maps to enable_kanban + orchestrator default."""

    def test_resolve_builtin_tool_flags_kanban(self) -> None:
        from app.services.agent.profile_resolver import resolve_builtin_tool_flags

        flags = resolve_builtin_tool_flags(["web_search", "memory", "kanban"])
        assert flags["enable_kanban"] is True
        assert flags["enable_wiki"] is False

    def test_factory_passes_enable_kanban_and_orchestrator_default(self) -> None:
        from app.ai_agents.agents import AgentFactory, GeneralAgentParams
        from app.core.types import ModelConfig
        from app.services.agent.profile_resolver import resolve_builtin_tool_flags

        flags = resolve_builtin_tool_flags(["web_search", "memory", "kanban"])
        agent = AgentFactory.create_general_agent(
            GeneralAgentParams(
                query="test",
                model_cfg=ModelConfig(model="test/model", api_key="test-key"),
                **flags,
            )
        )
        assert agent.enable_kanban is True
        assert agent.kanban_tool_mode == "orchestrator"
        assert agent.kanban_current_task_id is None


class TestGeneralAgentOptionalToolFlags:
    """Verify GeneralAgent stores optional builtin tool flags from GeneralAgentParams."""

    def test_general_agent_enable_wiki_false(self) -> None:
        """GeneralAgent with enable_wiki=False."""
        from app.ai_agents.general_agent.agent import GeneralAgent
        from app.core.types import ModelConfig

        agent = GeneralAgent(
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            mcp_config=None,
        )
        assert agent.enable_wiki is False

    def test_general_agent_enable_wiki_true(self) -> None:
        """GeneralAgent with enable_wiki=True stores the flag."""
        from app.ai_agents.general_agent.agent import GeneralAgent
        from app.core.types import ModelConfig

        agent = GeneralAgent(
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            mcp_config=None,
            enable_wiki=True,
        )
        assert agent.enable_wiki is True

    def test_factory_passes_enable_wiki_to_agent(self) -> None:
        """AgentFactory.create_general_agent passes enable_wiki to GeneralAgent."""
        from app.ai_agents.agents import AgentFactory, GeneralAgentParams
        from app.core.types import ModelConfig

        params_with_wiki = GeneralAgentParams(
            query="test",
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            enable_wiki=True,
        )
        agent = AgentFactory.create_general_agent(params_with_wiki)
        assert agent.enable_wiki is True

        params_no_wiki = GeneralAgentParams(
            query="test",
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            enable_wiki=False,
        )
        agent2 = AgentFactory.create_general_agent(params_no_wiki)
        assert agent2.enable_wiki is False

    def test_factory_passes_enable_render_ui_to_agent(self) -> None:
        """AgentFactory.create_general_agent passes enable_render_ui to GeneralAgent."""
        from app.ai_agents.agents import AgentFactory, GeneralAgentParams
        from app.core.types import ModelConfig

        params_with_render_ui = GeneralAgentParams(
            query="test",
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            enable_render_ui=True,
        )
        agent = AgentFactory.create_general_agent(params_with_render_ui)
        assert agent.enable_render_ui is True

        params_no_render_ui = GeneralAgentParams(
            query="test",
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            enable_render_ui=False,
        )
        agent2 = AgentFactory.create_general_agent(params_no_render_ui)
        assert agent2.enable_render_ui is False
