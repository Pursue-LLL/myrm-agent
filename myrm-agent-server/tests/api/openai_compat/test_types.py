"""Unit tests for OpenAI-compatible type definitions.

Validates Pydantic models serialize/deserialize correctly
per the OpenAI API specification.
"""

import pytest
from pydantic import ValidationError

from app.api.openai_compat.types import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ChoiceMessage,
    DeltaMessage,
    ModelListResponse,
    ModelObject,
    StreamChoice,
    UsageInfo,
)


def test_chat_message_basic():
    msg = ChatMessage(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"


def test_chat_message_multipart():
    msg = ChatMessage(
        role="user",
        content=[{"type": "text", "text": "describe this"}],
    )
    assert isinstance(msg.content, list)


def test_request_validation_minimal():
    req = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="hi")],
    )
    assert req.model == "default"
    assert req.stream is False
    assert req.temperature is None


def test_request_validation_full():
    req = ChatCompletionRequest(
        model="my-agent",
        messages=[
            ChatMessage(role="system", content="be helpful"),
            ChatMessage(role="user", content="hello"),
        ],
        temperature=0.7,
        top_p=0.9,
        max_tokens=100,
        stream=True,
        chat_id="session-123",
    )
    assert req.model == "my-agent"
    assert req.temperature == 0.7
    assert req.stream is True
    assert req.chat_id == "session-123"


def test_request_rejects_empty_messages():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(messages=[])


def test_request_rejects_invalid_temperature():
    with pytest.raises(ValidationError):
        ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="hi")],
            temperature=3.0,
        )


def test_response_has_defaults():
    resp = ChatCompletionResponse(
        choices=[Choice(message=ChoiceMessage(content="hi"))],
    )
    assert resp.object == "chat.completion"
    assert resp.id.startswith("chatcmpl-")
    assert resp.created > 0
    assert resp.usage.total_tokens == 0


def test_chunk_serialization():
    chunk = ChatCompletionChunk(
        id="chatcmpl-abc",
        model="test",
        choices=[StreamChoice(delta=DeltaMessage(content="hello"))],
    )
    data = chunk.model_dump()
    assert data["object"] == "chat.completion.chunk"
    assert data["choices"][0]["delta"]["content"] == "hello"


def test_model_list_response():
    resp = ModelListResponse(
        data=[
            ModelObject(id="default"),
            ModelObject(id="agent-1", owned_by="myrm/coder"),
        ]
    )
    assert resp.object == "list"
    assert len(resp.data) == 2
    assert resp.data[0].id == "default"


def test_usage_info():
    usage = UsageInfo(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    assert usage.total_tokens == 30
