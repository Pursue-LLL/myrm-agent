"""A tool call that arrives without an id still gets an error result when its tool fails.

The failure path builds a ``ToolMessage``, whose ``tool_call_id`` must be a string; an id of ``None`` used to
make that construction itself raise, so the model saw a pydantic error instead of the tool's failure.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
    _tool_interceptor_middleware_inner,
)

_MODULE = "myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware"


def _request(call_id: str | None) -> MagicMock:
    request = MagicMock()
    request.tool_call = {"name": "flaky_tool", "args": {}, "id": call_id}
    return request


async def _unreachable_handler(_req: object) -> ToolMessage:
    raise AssertionError("handler must not run; execute_with_retry is mocked")


async def _run_failing_tool(call_id: str | None) -> ToolMessage:
    pre_call = MagicMock()
    pre_call.blocked = False
    with (
        patch(f"{_MODULE}.run_pre_call_guards", return_value=pre_call),
        patch(f"{_MODULE}.execute_with_retry", AsyncMock(side_effect=ValueError("backend exploded"))),
        patch(f"{_MODULE}.get_token_tracker", return_value=None),
        patch(f"{_MODULE}.emit_tool_heartbeat", return_value=asyncio.create_task(asyncio.sleep(0))),
        patch("myrm_agent_harness.agent.middlewares._session_context.get_allowed_domains_map", return_value={}),
    ):
        result = await _tool_interceptor_middleware_inner(_request(call_id), _unreachable_handler)
    assert isinstance(result, ToolMessage)
    return result


@pytest.mark.asyncio
async def test_a_failing_tool_with_an_id_returns_an_error_message_for_that_id() -> None:
    result = await _run_failing_tool("call_7")

    assert result.status == "error"
    assert result.tool_call_id == "call_7"
    assert "backend exploded" in str(result.content)


@pytest.mark.asyncio
async def test_a_failing_tool_without_an_id_still_returns_an_error_message() -> None:
    result = await _run_failing_tool(None)

    assert result.status == "error"
    assert result.tool_call_id == ""
    assert "backend exploded" in str(result.content)
