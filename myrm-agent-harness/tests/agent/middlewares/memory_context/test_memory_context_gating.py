"""The middleware hands a request on untouched, and says why, when the block does not apply.

A call is left alone when the block is already in the request, there is no run context or no memory manager, the recall mode keeps memory out of the prompt, or the memory renders to nothing. Every case leaves ``not_applied`` and a reason for the server to show.

[INPUT]
- agent.middlewares.memory_context.memory_context_middleware::memory_context_middleware (POS: builds the block on every model call)
- agent.skill_agent.context::get_memory_runtime_injection (POS: the state and reason a call leaves for the server)

[POS]
Gate guard for the memory block's injection.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage, SystemMessage

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_format import (
    MEMORY_CONTEXT_MARKER,
    MemoryBlock,
    _memory_context_message,
)
from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import memory_context_middleware
from myrm_agent_harness.agent.skill_agent.context import (
    MemoryRuntimeBudget,
    get_memory_runtime_budget,
    get_memory_runtime_injection,
    set_memory_runtime_budget,
    set_memory_runtime_injection,
)
from myrm_agent_harness.toolkits.memory.config import RecallMode
from tests.support.memory_context_stubs import bound_manager, make_request

# The gauge an earlier call left behind: a call that skips injection must clear it, not leave it standing.
_LEFTOVER_BUDGET: MemoryRuntimeBudget = {
    "used": 120,
    "total": 1024,
    "rulesConfigured": 0,
    "rulesInjected": 0,
    "rulesTruncated": False,
}


async def test_skips_and_warns_when_the_block_is_already_in_the_request(caplog):
    handler = AsyncMock()
    req = make_request(
        messages=[
            SystemMessage(content="sys"),
            _memory_context_message(f"{MEMORY_CONTEXT_MARKER}>\ndata\n</user_memory_context>"),
            HumanMessage(content="hi"),
        ]
    )
    mock_manager = MagicMock()
    mock_manager.recall_mode = RecallMode.HYBRID
    with (
        caplog.at_level("WARNING"),
        bound_manager(mock_manager),
    ):
        await memory_context_middleware.awrap_model_call(req, handler)
    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "already_present",
    }
    assert "already present" in caplog.text


async def test_skips_when_no_runtime_context():
    handler = AsyncMock()
    req = make_request(has_runtime_context=False)
    await memory_context_middleware.awrap_model_call(req, handler)
    handler.assert_awaited_once_with(req)


async def test_sets_not_applied_reason_when_runtime_context_missing():
    handler = AsyncMock()
    req = make_request()
    req.runtime.context = None
    mock_manager = MagicMock()
    mock_manager.recall_mode = RecallMode.HYBRID
    set_memory_runtime_budget(_LEFTOVER_BUDGET)

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "missing_context",
    }
    assert get_memory_runtime_budget() is None


async def test_skips_when_no_memory_manager():
    handler = AsyncMock()
    req = make_request()
    set_memory_runtime_budget(_LEFTOVER_BUDGET)
    set_memory_runtime_injection({"state": "applied", "source": "snapshot"})
    with bound_manager(None):
        await memory_context_middleware.awrap_model_call(req, handler)
    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_budget() is None
    assert get_memory_runtime_injection() is None


async def test_sets_not_applied_reason_when_tools_recall_mode():
    handler = AsyncMock()
    req = make_request()
    mock_manager = MagicMock()
    mock_manager.recall_mode = RecallMode.TOOLS

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "recall_mode_tools",
    }


async def test_context_mode_cold_start_no_injection():
    """CONTEXT cold-start skips injection entirely — no learning guidance for unbound tools."""
    handler = AsyncMock()
    req = make_request(tools=[])

    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.CONTEXT
    mock_manager.get_context = AsyncMock(return_value={})

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "empty_context",
    }


async def test_short_circuits_when_format_returns_nothing():
    handler = AsyncMock()
    req = make_request()
    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value={})

    with (
        bound_manager(mock_manager),
        patch(
            "myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware._format_memory_context",
            return_value=MemoryBlock(None),
        ),
    ):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "empty_context",
    }


async def test_skips_injection_when_recall_mode_tools():
    """RecallMode.TOOLS should skip context injection entirely."""
    handler = AsyncMock()
    req = make_request()

    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.TOOLS

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    mock_manager.get_context.assert_not_called()
