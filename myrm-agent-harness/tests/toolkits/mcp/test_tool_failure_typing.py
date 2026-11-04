"""The timeout wrapper marks the failures it turns into text, so a caller that is not an LLM can tell them from results.

The wrapper's text is for a model to read, and the model path must keep receiving exactly that text. A Python script
calling the same tool through the IPC proxy is a different reader: it needs a failure to arrive as an error, which the
proxy can only do if the wrapper says which return values are failures.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.mcp.errors import MCPToolFailure
from myrm_agent_harness.toolkits.mcp.tool_processing import wrap_tools_with_timeout


def _wrapped(name: str, coroutine: object, *, timeout: float = 5.0) -> BaseTool:
    tool = MagicMock(spec=BaseTool)
    tool.name = name
    tool.coroutine = coroutine
    wrap_tools_with_timeout([tool], timeout=timeout)
    return tool


def _http_401() -> Exception:
    import httpx2

    response = MagicMock()
    response.status_code = 401
    return httpx2.HTTPStatusError("401 Unauthorized", request=MagicMock(), response=response)


class TestFailuresAreMarked:
    @pytest.mark.asyncio
    async def test_a_timeout_is_a_failure_with_the_text_the_model_reads(self) -> None:
        async def hangs(*args: object, **kwargs: object) -> str:
            await asyncio.sleep(10)
            return "never"

        result = await _wrapped("mcp__srv__slow", hangs, timeout=0.1).coroutine()

        assert isinstance(result, MCPToolFailure)
        assert str(result) == "MCP tool 'mcp__srv__slow' timed out after 0.1s. Server may be slow or unresponsive."

    @pytest.mark.asyncio
    async def test_unsupported_content_is_a_failure(self) -> None:
        result = await _wrapped(
            "mcp__srv__audio", AsyncMock(side_effect=NotImplementedError("AudioContent"))
        ).coroutine()

        assert isinstance(result, MCPToolFailure)
        assert "returned unsupported content" in result

    @pytest.mark.asyncio
    async def test_a_lost_authorization_is_a_failure(self) -> None:
        tool = _wrapped("mcp__auth_server__read", AsyncMock(side_effect=_http_401()))
        with patch("myrm_agent_harness.toolkits.mcp.tool_processing._emit_auth_expired_for_tool"):
            result = await tool.coroutine()

        assert isinstance(result, MCPToolFailure)
        assert "requires re-authorization" in result

    @pytest.mark.asyncio
    async def test_a_result_that_looks_like_a_failure_is_still_a_result(self) -> None:
        text = "MCP tool 'x' timed out after 1s. Server may be slow or unresponsive."
        result = await _wrapped("mcp__srv__echo", AsyncMock(return_value=text)).coroutine()

        assert not isinstance(result, MCPToolFailure)


class TestTheModelPathIsUnchanged:
    def test_a_failure_is_a_plain_string_to_every_consumer(self) -> None:
        failure = MCPToolFailure("boom")

        assert failure == "boom"
        assert ToolMessage(content=failure, tool_call_id="1").content == "boom"

    @pytest.mark.asyncio
    async def test_a_successful_result_carries_no_marker(self) -> None:
        result = await _wrapped("mcp__srv__echo", AsyncMock(return_value="fine")).coroutine()

        assert isinstance(result, str)
        assert not isinstance(result, MCPToolFailure)
        assert "fine" in result
