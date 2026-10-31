"""Live-path wiring tests for TwoLayerContextMiddleware (Layer 1 only)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage

from myrm_agent_harness.agent.middlewares.memory_context.two_layer_context_middleware import (
    _append_text_to_last_human,
    _injector,
    two_layer_context_middleware,
)
from myrm_agent_harness.core.context_vars import chat_id_var


@pytest.fixture(autouse=True)
def _reset_injector_session() -> None:
    _injector.reset_session("chat-two-layer-1")
    yield
    _injector.reset_session("chat-two-layer-1")


@pytest.mark.asyncio
async def test_middleware_appends_base_context_without_mutating_system(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_TWO_LAYER_CONTEXT_LIVE", raising=False)
    session_id = "chat-two-layer-1"
    token = chat_id_var.set(session_id)
    try:
        frozen = "frozen system prefix"
        request = ModelRequest(
            messages=[
                SystemMessage(content=frozen),
                HumanMessage(content="Continue the rollout checklist."),
            ],
            model=MagicMock(),
        )
        captured: list[ModelRequest] = []

        async def handler(req: ModelRequest) -> ModelResponse:
            captured.append(req)
            return ModelResponse(result=[])

        await two_layer_context_middleware.awrap_model_call(request, handler)
    finally:
        chat_id_var.reset(token)

    assert len(captured) == 1
    assert captured[0].messages[0].content == frozen
    last_human = captured[0].messages[-1]
    assert isinstance(last_human, HumanMessage)
    tail = str(last_human.content)
    assert "<base_context" in tail
    assert "Continue the rollout checklist." in tail


@pytest.mark.asyncio
async def test_middleware_noop_without_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_TWO_LAYER_CONTEXT_LIVE", raising=False)
    request = ModelRequest(
        messages=[HumanMessage(content="hello")],
        model=MagicMock(),
    )
    handler = AsyncMock(return_value=ModelResponse(result=[]))
    await two_layer_context_middleware.awrap_model_call(request, handler)
    handler.assert_awaited_once_with(request)


@pytest.mark.asyncio
async def test_middleware_respects_disable_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_TWO_LAYER_CONTEXT_LIVE", "0")
    session_id = "chat-two-layer-1"
    token = chat_id_var.set(session_id)
    try:
        request = ModelRequest(
            messages=[HumanMessage(content="hello")],
            model=MagicMock(),
        )
        handler = AsyncMock(return_value=ModelResponse(result=[]))
        await two_layer_context_middleware.awrap_model_call(request, handler)
        handler.assert_awaited_once_with(request)
    finally:
        chat_id_var.reset(token)


_IMAGE_PART = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


async def _messages_sent_to_model(messages: list[AnyMessage]) -> list[AnyMessage]:
    token = chat_id_var.set("chat-two-layer-1")
    captured: list[ModelRequest] = []

    async def handler(req: ModelRequest) -> ModelResponse:
        captured.append(req)
        return ModelResponse(result=[])

    try:
        await two_layer_context_middleware.awrap_model_call(ModelRequest(messages=messages, model=MagicMock()), handler)
    finally:
        chat_id_var.reset(token)
    return captured[0].messages


@pytest.mark.asyncio
async def test_multimodal_question_keeps_every_original_part_and_gains_one_text_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYRM_TWO_LAYER_CONTEXT_LIVE", raising=False)
    question = [{"type": "text", "text": "What is in this picture?"}, _IMAGE_PART]

    sent = await _messages_sent_to_model([SystemMessage(content="frozen"), HumanMessage(content=question)])

    parts = sent[-1].content
    assert isinstance(parts, list)
    assert parts[:2] == question
    assert len(parts) == 3
    tail = parts[2]
    assert isinstance(tail, dict)
    assert tail["type"] == "text"
    assert "<base_context" in str(tail["text"])


@pytest.mark.asyncio
async def test_a_stale_base_context_block_on_the_question_is_replaced_not_stacked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYRM_TWO_LAYER_CONTEXT_LIVE", raising=False)
    stale = '<base_context cache_hash="stale" turn="0"><session_summary>old</session_summary></base_context>'

    sent = await _messages_sent_to_model([HumanMessage(content=f"Continue the checklist.\n\n{stale}")])

    tail = str(sent[-1].content)
    assert tail.startswith("Continue the checklist.\n\n<base_context")
    assert tail.count("<base_context ") == 1
    assert 'cache_hash="stale"' not in tail


def test_without_a_human_message_there_is_nothing_to_append_to() -> None:
    assert _append_text_to_last_human([SystemMessage(content="frozen")], "<base_context/>") is None
