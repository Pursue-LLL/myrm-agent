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
    build_signoff_clarify_deterministic_model,
)


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class _Request:
    state: dict[str, list[object]]
    tools: list[_FakeTool]
    tool_choice: str = "auto"
    model: object | None = None

    def __init__(self, messages: list[object], tools: list[_FakeTool]) -> None:
        self.state = {"messages": messages}
        self.tools = tools

    def override(self, **kwargs: object) -> "_Request":
        clone = _Request(list(self.state["messages"]), list(self.tools))
        if "tool_choice" in kwargs:
            clone.tool_choice = str(kwargs["tool_choice"])
        if "model" in kwargs:
            clone.model = kwargs["model"]
        return clone


@pytest.mark.asyncio
async def test_signoff_clarify_contract_h2d_always_uses_stub_model() -> None:
    middleware = SignoffClarifyContractMiddleware(enabled=True)
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    await middleware.awrap_model_call(
        _Request(
            [HumanMessage(content="hi")],
            [_FakeTool("ask_question_tool"), _FakeTool("web_search")],
        ),
        handler,  # type: ignore[arg-type]
    )

    handler.assert_awaited_once()
    call_request = handler.await_args.args[0]
    model = getattr(call_request, "model", None)
    assert model is not None
    assert getattr(model, "_llm_type", "") == "signoff_clarify_deterministic"


def test_signoff_clarify_contract_sync_wrap_uses_stub_model() -> None:
    middleware = SignoffClarifyContractMiddleware(enabled=True)
    seen: list[object] = []

    def handler(request: _Request) -> ModelResponse:
        seen.append(getattr(request, "model", None))
        return ModelResponse(result=[])

    middleware.wrap_model_call(
        _Request(
            [HumanMessage(content="hi")],
            [_FakeTool("ask_question_tool")],
        ),
        handler,  # type: ignore[arg-type]
    )

    assert len(seen) == 1
    model = seen[0]
    assert model is not None
    assert getattr(model, "_llm_type", "") == "signoff_clarify_deterministic"


@pytest.mark.asyncio
async def test_signoff_clarify_contract_raises_when_tool_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYRM_E2E_SIGNOFF_CLARIFY_POOL", raising=False)
    middleware = SignoffClarifyContractMiddleware(enabled=True)
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    with pytest.raises(RuntimeError, match="ask_question_tool not mounted"):
        await middleware.awrap_model_call(
            _Request([HumanMessage(content="hi")], [_FakeTool("web_search")]),
            handler,  # type: ignore[arg-type]
        )
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_signoff_clarify_contract_pool_skips_tool_presence_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "1")
    middleware = SignoffClarifyContractMiddleware(enabled=True)
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    await middleware.awrap_model_call(
        _Request([HumanMessage(content="hi")], [_FakeTool("web_search")]),
        handler,  # type: ignore[arg-type]
    )
    handler.assert_awaited_once()


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


def test_signoff_clarify_deterministic_model_bind_tools_returns_self() -> None:
    model = build_signoff_clarify_deterministic_model()
    bound = model.bind_tools([object()], tool_choice="auto")
    assert bound is model


@pytest.mark.asyncio
async def test_signoff_clarify_deterministic_model_emits_tool_call() -> None:
    model = build_signoff_clarify_deterministic_model()
    result = await model._agenerate([])
    msg = result.generations[0].message
    assert isinstance(msg, AIMessage)
    assert msg.tool_calls[0]["name"] == "ask_question_tool"
    assert msg.tool_calls[0]["args"] == SIGNOFF_CLARIFY_FORM_ARGS
