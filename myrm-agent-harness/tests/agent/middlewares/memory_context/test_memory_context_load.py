"""A memory load that fails, hangs or returns something unusable leaves the request alone instead of failing the model call.

[INPUT]
- agent.middlewares.memory_context.memory_context_middleware::memory_context_middleware (POS: loads the memory and builds the block on every model call)
- agent.skill_agent.context::get_memory_runtime_injection (POS: the state and reason a call leaves for the server)

[POS]
Fail-open guard for the memory load: the call goes on without the block and the reason is recorded.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import memory_context_middleware
from myrm_agent_harness.agent.skill_agent.context import get_memory_runtime_injection
from myrm_agent_harness.toolkits.memory.config import RecallMode
from tests.support.memory_context_stubs import bound_manager, make_request


async def test_get_context_failure_returns_without_leak_warnings():
    """When static memory context load fails, middleware degrades to not_applied/load_error."""
    handler = AsyncMock()
    req = make_request()
    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.HYBRID

    async def exploding_get_context(*args: object, **_: object) -> dict[str, object]:
        raise RuntimeError("simulated_load_failure")

    mock_manager.get_context = exploding_get_context

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "load_error",
    }


async def test_handles_static_context_failure():
    handler = AsyncMock()
    req = make_request()

    mock_manager = MagicMock()
    mock_manager.user_id = "u123"
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(side_effect=RuntimeError("db error"))

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "load_error",
    }


async def test_handles_get_context_load_error():
    handler = AsyncMock()
    req = make_request()

    mock_manager = MagicMock()
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(side_effect=RuntimeError("static db error"))

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "load_error",
    }


async def test_handles_invalid_static_payload_type():
    handler = AsyncMock()
    req = make_request()

    mock_manager = MagicMock()
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value="not-a-dict")

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "invalid_static_payload",
    }


async def test_timeout_fails_open_not_applied():
    handler = AsyncMock()
    req = make_request()

    async def _hanging_get_context(**kwargs):
        await asyncio.sleep(0.5)
        return {}

    mock_manager = MagicMock()
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = _hanging_get_context
    mock_manager._config.retrieval.timeout_seconds = 0.05

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "load_timeout",
    }


async def test_static_context_error_fails_open():
    """manager.get_context returning a BaseException must fail open, not crash."""
    handler = AsyncMock()
    req = make_request()

    mock_manager = MagicMock()
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value=RuntimeError("static retrieval exploded"))

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "static_error",
    }


async def test_static_context_unexpected_type_fails_open():
    """manager.get_context returning a non-dict non-exception payload fails open."""
    handler = AsyncMock()
    req = make_request()

    mock_manager = MagicMock()
    mock_manager.recall_mode = RecallMode.HYBRID
    mock_manager.get_context = AsyncMock(return_value=["not", "a", "dict"])

    with bound_manager(mock_manager):
        await memory_context_middleware.awrap_model_call(req, handler)

    handler.assert_awaited_once_with(req)
    assert get_memory_runtime_injection() == {
        "state": "not_applied",
        "reason": "invalid_static_payload",
    }
