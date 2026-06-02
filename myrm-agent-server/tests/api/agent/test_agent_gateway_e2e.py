"""Agent Tool Gateway 配置端到端测试

验证 tool_gateway_config 在 Agent CRUD 和消息请求链路中的完整行为。
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
    resp = httpx.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={
            "username": os.getenv("TEST_USERNAME", "test"),
            "password": os.getenv("TEST_PASSWORD", "test"),
        },
        timeout=10,
    )
    if resp.status_code == 200:
        token = resp.json().get("data", {}).get("access_token")
        if token:
            return {"Authorization": f"Bearer {token}"}
    return {}


@pytest.fixture
def created_agent_id(auth_headers: dict[str, str]):
    """Create an agent and return its ID; delete after test."""
    payload = {
        "name": "Test Gateway Agent",
        "description": "E2E test for tool_gateway_config",
        "system_prompt": "You are a test agent.",
        "mcp_ids": [],
        "skill_ids": [],
        "tool_gateway_config": {
            "use_gateway": True,
            "gateway_url": "https://api.test.myrm.ai/v1/gateway",
            "auth_token": "test_pat_token",
        },
    }
    resp = httpx.post(
        f"{BASE_URL}/api/v1/user-agents",
        json=payload,
        headers=auth_headers,
        timeout=10,
    )
    assert resp.status_code == 200
    agent_id = resp.json()["data"]["id"]
    yield agent_id

    # Cleanup
    httpx.delete(
        f"{BASE_URL}/api/v1/user-agents/{agent_id}",
        headers=auth_headers,
        timeout=10,
    )


@_skip_e2e
class TestAgentGatewayConfigE2E:
    def test_create_agent_with_gateway_config(self, auth_headers: dict[str, str], created_agent_id: str) -> None:
        """Create an agent with gateway config and verify persistence."""
        resp = httpx.get(
            f"{BASE_URL}/api/v1/user-agents/{created_agent_id}",
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        agent = resp.json()["data"]
        assert agent["tool_gateway_config"] is not None
        assert agent["tool_gateway_config"]["use_gateway"] is True
        assert agent["tool_gateway_config"]["gateway_url"] == "https://api.test.myrm.ai/v1/gateway"
        assert agent["tool_gateway_config"]["auth_token"] == "test_pat_token"

    def test_update_agent_gateway_config(self, auth_headers: dict[str, str], created_agent_id: str) -> None:
        """Update agent's gateway config and verify the change persists."""
        update_payload = {
            "tool_gateway_config": {
                "use_gateway": False,
                "gateway_url": "https://other.myrm.ai",
                "auth_token": "new_token",
            }
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
        assert agent["tool_gateway_config"] is not None
        assert agent["tool_gateway_config"]["use_gateway"] is False
        assert agent["tool_gateway_config"]["gateway_url"] == "https://other.myrm.ai"
        assert agent["tool_gateway_config"]["auth_token"] == "new_token"

    def test_create_agent_without_gateway_config(self, auth_headers: dict[str, str]) -> None:
        """Create an agent without specifying gateway config — should be null."""
        payload = {
            "name": "No Gateway Agent",
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
        assert agent.get("tool_gateway_config") is None

        httpx.delete(
            f"{BASE_URL}/api/v1/user-agents/{agent_id}",
            headers=auth_headers,
            timeout=10,
        )


class TestAgentGatewayConfigInternal:
    """Test tool_gateway_config field in internal models."""

    def test_agent_config_request_default(self) -> None:
        """Verify AgentConfigRequest defaults to None for tool_gateway_config."""
        from app.services.agent.params import AgentConfigRequest

        cfg = AgentConfigRequest()
        assert cfg.tool_gateway_config is None

    def test_agent_config_request_custom(self) -> None:
        """Verify AgentConfigRequest accepts custom tool_gateway_config."""
        from myrm_agent_harness.core.config.gateway import ToolGatewayConfig

        from app.services.agent.params import AgentConfigRequest

        gateway_cfg = ToolGatewayConfig(use_gateway=True, gateway_url="http://gw", auth_token="token")
        cfg = AgentConfigRequest(tool_gateway_config=gateway_cfg)
        assert cfg.tool_gateway_config is not None
        assert cfg.tool_gateway_config.use_gateway is True
        assert cfg.tool_gateway_config.gateway_url == "http://gw"
        assert cfg.tool_gateway_config.auth_token == "token"

    def test_general_agent_params_gateway_config(self) -> None:
        """Verify GeneralAgentParams accepts tool_gateway_config."""
        from myrm_agent_harness.core.config.gateway import ToolGatewayConfig

        from app.ai_agents.agents import GeneralAgentParams
        from app.core.types import ModelConfig

        gateway_cfg = ToolGatewayConfig(use_gateway=True, gateway_url="http://gw", auth_token="token")
        params = GeneralAgentParams(
            query="test",
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            tool_gateway_config=gateway_cfg.model_dump(mode="json"),
        )
        assert params.tool_gateway_config is not None
        assert params.tool_gateway_config["use_gateway"] is True

    def test_factory_passes_gateway_config_to_agent(self) -> None:
        """AgentFactory.create_general_agent passes tool_gateway_config to SearchServiceConfig."""
        from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
        from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

        from app.ai_agents.agents import AgentFactory, GeneralAgentParams
        from app.core.types import ModelConfig

        gateway_cfg = ToolGatewayConfig(use_gateway=True, gateway_url="http://gw", auth_token="token")
        params = GeneralAgentParams(
            query="test",
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            tool_gateway_config=gateway_cfg.model_dump(mode="json"),
            search_service_cfg=SearchServiceConfig(search_service="tavily", api_key="test"),
        )
        agent = AgentFactory.create_general_agent(params)
        assert agent.search_service_cfg is not None
        assert agent.search_service_cfg.gateway_config is not None
        assert agent.search_service_cfg.gateway_config.use_gateway is True
        assert agent.search_service_cfg.gateway_config.gateway_url == "http://gw"
        assert agent.search_service_cfg.gateway_config.auth_token == "token"
