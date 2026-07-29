"""Unit tests for signoff clarify contract middleware and core."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from app.ai_agents.general_agent.agent_middlewares.signoff_clarify_contract_middleware import (
    SignoffClarifyContractMiddleware,
)
from app.ai_agents.general_agent.signoff_clarify_contract_core import (
    SIGNOFF_CLARIFY_FORM_ARGS,
    build_signoff_clarify_ai_message,
)


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class _Request:
    state: dict[str, list[object]]
    tools: list[_FakeTool]
    tool_choice: str = "auto"

    def __init__(self, messages: list[object], tools: list[_FakeTool]) -> None:
        self.state = {"messages": messages}
        self.tools = tools

    def override(self, **kwargs: object) -> "_Request":
        clone = _Request(list(self.state["messages"]), list(self.tools))
        clone.tool_choice = str(kwargs.get("tool_choice", self.tool_choice))
        return clone


@pytest.mark.asyncio
async def test_signoff_clarify_contract_forces_first_turn_tool_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_E2E_SIGNOFF_CLARIFY_POOL", raising=False)
    middleware = SignoffClarifyContractMiddleware(enabled=True)
    captured: dict[str, object] = {}

    async def handler(request: object) -> object:
        captured["tool_choice"] = getattr(request, "tool_choice", None)
        return object()

    await middleware.awrap_model_call(
        _Request([HumanMessage(content="hi")], [_FakeTool("ask_question_tool")]),
        handler,  # type: ignore[arg-type]
    )
    assert captured["tool_choice"] == "required"


@pytest.mark.asyncio
async def test_signoff_clarify_contract_h2b_deterministic_no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "1")
    middleware = SignoffClarifyContractMiddleware(enabled=True)
    handler = AsyncMock(return_value="ok")

    result = await middleware.awrap_model_call(
        _Request(
            [HumanMessage(content="hi")],
            [_FakeTool("ask_question_tool"), _FakeTool("web_search")],
        ),
        handler,  # type: ignore[arg-type]
    )

    handler.assert_not_awaited()
    assert isinstance(result, ModelResponse)
    assert len(result.result) == 1
    msg = result.result[0]
    assert isinstance(msg, AIMessage)
    assert msg.tool_calls
    assert msg.tool_calls[0]["name"] == "ask_question_tool"
    assert msg.tool_calls[0]["args"] == SIGNOFF_CLARIFY_FORM_ARGS


@pytest.mark.asyncio
async def test_signoff_clarify_contract_skips_after_ai_message() -> None:
    middleware = SignoffClarifyContractMiddleware(enabled=True)
    handler = AsyncMock(return_value="ok")

    result = await middleware.awrap_model_call(
        _Request(
            [HumanMessage(content="hi"), AIMessage(content="")],
            [_FakeTool("ask_question_tool")],
        ),
        handler,  # type: ignore[arg-type]
    )
    assert result == "ok"
    handler.assert_awaited_once()


def test_build_signoff_clarify_ai_message_matches_contract() -> None:
    msg = build_signoff_clarify_ai_message()
    assert isinstance(msg, AIMessage)
    assert len(msg.tool_calls) == 1
    args = msg.tool_calls[0]["args"]
    assert args["title"] == "Pick stack"
    questions = args["questions"]
    assert isinstance(questions, list)
    assert questions[0]["id"] == "stack"
