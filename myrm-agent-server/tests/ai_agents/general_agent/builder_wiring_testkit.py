"""Shared stand-ins for the ``build_general_agent`` wiring tests.

A real ``GeneralAgent`` carries the flags; the builder runs for real around it. Only what reaches outside the process is
stood in for: the LLM clients, the skill storage, the sandbox, the harness constructor and the services each branch reads.
Every tool setup of the wrapper is replaced by a recorder that mounts a tool named after itself, so what the harness is
allowed to call is exactly what the flags asked for.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.ai_agents.general_agent import GeneralAgent
from app.ai_agents.general_agent.factory import build_general_agent
from app.core.types.business import MCPServerConfig, ModelConfig

BUILDER = "app.ai_agents.general_agent.factory.builder"
CHAT_ID = "chat-build"

SETUP_METHODS = {
    "_setup_search_and_basic_tools": ("search", False),
    "_setup_clarification_tools": ("clarification", False),
    "_setup_artifact_publish_tool": ("artifact_publish", True),
    "_setup_cron_tools": ("cron", True),
    "_setup_browser_tools": ("browser", True),
    "_setup_computer_use_tools": ("computer_use", False),
    "_setup_external_agents": ("external_agents", True),
    "_setup_skill_market_tool": ("skill_market", False),
    "_setup_skill_manage_tool": ("skill_manage", False),
}
BASE_TOOLS = ["search", "clarification", "artifact_publish"]


def mcp_server(name: str) -> MCPServerConfig:
    return MCPServerConfig(name=name, type="sse", url=f"https://{name}.example/sse")


class BuilderHarness:
    """A real wrapper, the real builder, and stand-ins at the boundary; ``create`` records what the harness is handed."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.monkeypatch = monkeypatch
        self.llm = MagicMock(name="llm")
        self.skill_backend = MagicMock(name="skill_backend")
        self.skill_backend.list_skills = AsyncMock(return_value=[])
        self.skill_cfg = SimpleNamespace(trusted_skill_ids=None, skill_env_vars=None)
        self.skill_runtime = SimpleNamespace(
            storage_backend=MagicMock(name="storage"),
            user_skill_cfg=self.skill_cfg,
            runtime_skill_ids=["alpha"],
            skill_backend=self.skill_backend,
        )
        self.llm_bundle = SimpleNamespace(
            llm=self.llm,
            fallback_llm=None,
            safety_fallback_llm=None,
            stream_fallback_llms=None,
            privacy_routing_cfg=None,
            lite_llm=None,
        )
        self.agent = MagicMock(name="skill_agent")
        self.agent.budget_checker = None
        self.create = AsyncMock(return_value=self.agent)
        self.runtime = SimpleNamespace(
            executor=MagicMock(name="executor"),
            memory_ext=object(),
            pre_compact_ext=object(),
            archive_checkpoint_ext=object(),
        )
        self.build_sandbox = AsyncMock(return_value=self.runtime)
        self.calls: dict[str, list[tuple[tuple[object, ...], dict[str, object]]]] = {
            name: [] for name, _ in SETUP_METHODS.values()
        }
        self._stand_in_for_the_boundary()

    def patch(self, target: str, value: object) -> None:
        self.monkeypatch.setattr(target, value)

    def _stand_in_for_the_boundary(self) -> None:
        self.patch(f"{BUILDER}.initialize_agent_llms", AsyncMock(return_value=self.llm_bundle))
        self.patch(f"{BUILDER}.load_skill_runtime", AsyncMock(return_value=self.skill_runtime))
        self.patch(f"{BUILDER}.build_sandbox_runtime", self.build_sandbox)
        self.patch(f"{BUILDER}.build_agent_middlewares", AsyncMock(return_value=[]))
        self.patch(f"{BUILDER}.build_system_prompt", MagicMock(return_value="system prompt"))
        self.patch(f"{BUILDER}._should_enable_cron_tools", lambda: True)
        self.patch(f"{BUILDER}._should_enable_subagent_tools", lambda: True)
        self.patch("app.platform_utils.get_checkpointer", MagicMock(return_value=InMemorySaver()))
        self.patch("myrm_agent_harness.api.create_skill_agent", self.create)
        self.patch("app.core.skills.state_manager_instance.get_state_manager", lambda: None)
        self.patch("app.services.budget.enforcer.get_budget_guard", AsyncMock(return_value=None))

    def wrapper(self, **params: object) -> GeneralAgent:
        """A real wrapper whose tool setups are recorders; flags are the ``GeneralAgentParams`` ones."""
        fields: dict[str, object] = {
            "model_cfg": ModelConfig(model="gpt-4o", api_key="test-key"),
            "query": "hello",
            "chat_id": CHAT_ID,
            "enable_memory": False,
            "enable_browser": False,
            "prompt_mode": "full",
            **params,
        }
        wrapper = AgentFactory.create_general_agent(GeneralAgentParams(**fields))
        for method, (tool_name, is_async) in SETUP_METHODS.items():
            self.monkeypatch.setattr(wrapper, method, self._recorder(tool_name, is_async))
        return wrapper

    def _recorder(self, tool_name: str, is_async: bool) -> Callable[..., object]:
        def record(tools: list[object], *args: object, **kwargs: object) -> None:
            self.calls[tool_name].append(((tools, *args), kwargs))
            tools.append(SimpleNamespace(name=tool_name))

        async def record_async(tools: list[object], *args: object, **kwargs: object) -> None:
            record(tools, *args, **kwargs)

        return record_async if is_async else record

    async def build(self, wrapper: GeneralAgent, **kwargs: object) -> dict[str, object]:
        """Run the builder; returns the keyword arguments the harness constructor received."""
        built = await build_general_agent(wrapper, CHAT_ID, **kwargs)
        assert built is self.agent
        return self.create.await_args.kwargs

    def mounted(self) -> list[str]:
        return [name for name, calls in self.calls.items() if calls]


def allowed_tools(handed: dict[str, object]) -> list[str]:
    return list(handed["spec"].allowed_tools)
