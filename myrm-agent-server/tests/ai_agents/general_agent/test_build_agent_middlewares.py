"""The middleware stack of a built GeneralAgent is assembled by actually running the factory step.

[INPUT]
- app/ai_agents/general_agent/factory/middlewares.py::build_agent_middlewares (POS: unit under test, executed for real)

[OUTPUT]
- Tests that the step returns an ordered stack with the guardrail first and the Human-tail blocks last.

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
)
from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.ai_agents.general_agent.factory.middlewares import build_agent_middlewares
from app.ai_agents.general_agent.factory.runtime import SandboxRuntime
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


@pytest.mark.asyncio
async def test_the_stack_is_assembled_with_the_guardrail_first_and_the_tail_blocks_last() -> None:
    wrapper = AgentFactory.create_general_agent(
        GeneralAgentParams(
            model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
            query="assemble the stack",
            chat_id=_CHAT_ID,
            enable_browser=False,
            prompt_mode="full",
        )
    )

    middlewares = await build_agent_middlewares(
        wrapper,
        _CHAT_ID,
        _runtime(),
        lite_llm=FakeListChatModel(responses=["ok"]),
    )

    assert isinstance(middlewares[0], GuardrailMiddleware)
    assert middlewares[-2:] == [proactive_pack_middleware, ephemeral_delta_middleware]
