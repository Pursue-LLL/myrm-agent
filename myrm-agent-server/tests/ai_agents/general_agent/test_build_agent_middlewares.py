"""The middleware stack of a built GeneralAgent is assembled by actually running the factory step.

[INPUT]
- app/ai_agents/general_agent/factory/middlewares.py::build_agent_middlewares (POS: unit under test, executed for real)

[OUTPUT]
- Tests that the step returns an ordered stack with the guardrail first and the Human-tail blocks last, and
  that the widget declaration is mounted exactly when the mount plan says so.

[POS]
The mount-order tests read this module's source; only a call proves that every name the function uses at runtime
exists at runtime (a type that is imported for the type checker alone cannot be evaluated by ``cast``).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from myrm_agent_harness.agent.middlewares.guardrails import GuardrailMiddleware

from app.ai_agents.agent_middlewares import (
    ephemeral_delta_middleware,
    proactive_pack_middleware,
    widget_capability_middleware,
)
from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.ai_agents.general_agent.factory.middlewares import build_agent_middlewares
from app.ai_agents.general_agent.factory.runtime import SandboxRuntime
from app.ai_agents.general_agent.mount_resolver import ResolvedMountPlan
from app.core.types.business import ModelConfig

_CHAT_ID = "middleware-stack-chat"


def _runtime() -> SandboxRuntime:
    return SandboxRuntime(
        executor=MagicMock(),
        compress_offload_cb=MagicMock(),
        context_snapshot_cb=MagicMock(),
        compress_eviction_cb=None,
        pre_compact_cb=None,
        archive_checkpoint_store=None,
        archive_checkpoint_notifier=None,
        memory_ext=MagicMock(),
        pre_compact_ext=MagicMock(),
        archive_checkpoint_ext=MagicMock(),
    )


def _plan(*, widget: bool) -> ResolvedMountPlan:
    return ResolvedMountPlan(
        mount_browser=False,
        mount_computer_use=False,
        mount_desktop_prompt=False,
        mount_widget_capability=widget,
    )


async def _build(*, widget: bool) -> list[object]:
    wrapper = AgentFactory.create_general_agent(
        GeneralAgentParams(
            model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
            query="assemble the stack",
            chat_id=_CHAT_ID,
            enable_browser=False,
            prompt_mode="full",
        )
    )
    return await build_agent_middlewares(
        wrapper,
        _CHAT_ID,
        _runtime(),
        lite_llm=FakeListChatModel(responses=["ok"]),
        mount_plan=_plan(widget=widget),
    )


@pytest.mark.asyncio
async def test_the_stack_is_assembled_with_the_guardrail_first_and_the_tail_blocks_last() -> None:
    middlewares = await _build(widget=True)

    assert isinstance(middlewares[0], GuardrailMiddleware)
    assert middlewares[-2:] == [proactive_pack_middleware, ephemeral_delta_middleware]


@pytest.mark.asyncio
async def test_the_widget_declaration_is_mounted_exactly_when_the_plan_says_so() -> None:
    assert widget_capability_middleware in await _build(widget=True)
    assert widget_capability_middleware not in await _build(widget=False)
