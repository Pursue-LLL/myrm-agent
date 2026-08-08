"""Integration tests for /v1/chat/completions endpoint.

Tests both streaming and non-streaming modes with mocked Agent execution.
"""

import json
from collections.abc import AsyncIterable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="openai_compat_only", openai_compat=True)
@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def api_key(client: AsyncClient) -> str:
    """Create a valid API key for tests."""
    resp = await client.post("/api/v1/api-keys", json={"name": "Completions Test"})
    return resp.json()["key"]


async def _mock_agent_stream(*args, **kwargs) -> AsyncIterable[dict[str, object]]:
    """Simulate Agent stream events as async generator."""
    yield {"type": "message_chunk", "content": "Hello"}
    yield {"type": "message_chunk", "content": " world!"}
    yield {"type": "message_end", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def _make_mock_params():
    """Create a minimal mock for GeneralAgentParams."""
    params = MagicMock()
    params.model_cfg = MagicMock()
    params.chat_id = "test-chat"
    return params


@pytest.mark.asyncio
async def test_completions_non_streaming(client: AsyncClient, api_key: str):
    """Non-streaming should return a complete JSON response."""
    with (
        patch(
            "app.api.openai_compat.completions.ai_agent_service_stream",
            new=_mock_agent_stream,
        ),
        patch(
            "app.api.openai_compat.completions._build_agent_params",
            new_callable=AsyncMock,
            return_value=_make_mock_params(),
        ),
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "default",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Hello world!"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_completions_streaming(client: AsyncClient, api_key: str):
    """Streaming should return SSE chunks in OpenAI format."""

    async def mock_stream_iter(*a, **kw):
        yield {"type": "message_chunk", "content": "Hi"}
        yield {"type": "message_chunk", "content": " there"}
        yield {"type": "message_end", "usage": {}}

    with (
        patch(
            "app.api.openai_compat.completions.ai_agent_service_stream",
            new=mock_stream_iter,
        ),
        patch(
            "app.api.openai_compat.completions._build_agent_params",
            new_callable=AsyncMock,
            return_value=_make_mock_params(),
        ),
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "default",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    lines = resp.text.strip().split("\n\n")
    chunks = []
    for line in lines:
        if line.startswith("data: ") and line != "data: [DONE]":
            chunks.append(json.loads(line[6:]))

    # First chunk has role
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"

    # Content chunks
    content_chunks = [c for c in chunks if c["choices"][0]["delta"].get("content")]
    assert len(content_chunks) >= 1

    # Last meaningful chunk has finish_reason
    final_chunks = [c for c in chunks if c["choices"][0].get("finish_reason") == "stop"]
    assert len(final_chunks) == 1

    # Ends with [DONE]
    assert lines[-1] == "data: [DONE]"


@pytest.mark.asyncio
async def test_completions_non_streaming_agent_message_event(client: AsyncClient, api_key: str):
    """Non-streaming should collect text from Agent `message` events (production format)."""
    with (
        patch(
            "app.api.openai_compat.completions.ai_agent_service_stream",
            new=_mock_agent_stream_message_events,
        ),
        patch(
            "app.api.openai_compat.completions._build_agent_params",
            new_callable=AsyncMock,
            return_value=_make_mock_params(),
        ),
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "default",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["choices"][0]["message"]["content"] == "Hello world!"


async def _mock_agent_stream_message_events(*args, **kwargs) -> AsyncIterable[dict[str, object]]:
    """Simulate production Agent stream events (`message` + `data`)."""
    yield {"type": "message", "data": "Hello"}
    yield {"type": "message", "data": " world!"}
    yield {"type": "message_end", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


@pytest.mark.asyncio
async def test_completions_streaming_agent_message_event(client: AsyncClient, api_key: str):
    """Streaming should emit content chunks from Agent `message` events."""

    async def mock_stream_iter(*a, **kw):
        yield {"type": "message", "data": "Hi"}
        yield {"type": "message", "data": " there"}
        yield {"type": "message_end", "usage": {}}

    with (
        patch(
            "app.api.openai_compat.completions.ai_agent_service_stream",
            new=mock_stream_iter,
        ),
        patch(
            "app.api.openai_compat.completions._build_agent_params",
            new_callable=AsyncMock,
            return_value=_make_mock_params(),
        ),
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "default",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

    assert resp.status_code == 200
    lines = resp.text.strip().split("\n\n")
    chunks = [json.loads(line[6:]) for line in lines if line.startswith("data: ") and line != "data: [DONE]"]
    content_chunks = [c for c in chunks if c["choices"][0]["delta"].get("content")]
    assert "".join(c["choices"][0]["delta"]["content"] for c in content_chunks) == "Hi there"


@pytest.mark.asyncio
async def test_completions_unauthorized(client: AsyncClient):
    """Missing auth should return 401."""
    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "default",
            "messages": [{"role": "user", "content": "test"}],
        },
    )
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "unsafe_chat_id",
    [
        "../../etc/passwd",
        "chat_../../etc",
        "..\\..\\windows\\system32",
        "foo/bar",
    ],
)
@pytest.mark.asyncio
async def test_completions_rejects_unsafe_chat_id_non_streaming(
    client: AsyncClient, api_key: str, unsafe_chat_id: str
):
    """Path-traversal chat_ids must fail fast with 400 before any agent work."""
    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "default",
            "messages": [{"role": "user", "content": "Hello"}],
            "chat_id": unsafe_chat_id,
            "stream": False,
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert resp.status_code == 400
    assert "chat_id" in resp.text


@pytest.mark.asyncio
async def test_completions_rejects_unsafe_chat_id_streaming(
    client: AsyncClient, api_key: str
):
    """Streaming must also reject unsafe chat_ids with 400 before opening SSE."""
    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "default",
            "messages": [{"role": "user", "content": "Hello"}],
            "chat_id": "../../etc/passwd",
            "stream": True,
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )

    assert resp.status_code == 400
    assert "chat_id" in resp.text


@pytest.mark.asyncio
async def test_completions_accepts_safe_custom_chat_id(client: AsyncClient, api_key: str):
    """Safe custom chat_ids must pass the whitelist and reach the agent flow."""
    with (
        patch(
            "app.api.openai_compat.completions.ai_agent_service_stream",
            new=_mock_agent_stream,
        ),
        patch(
            "app.api.openai_compat.completions._build_agent_params",
            new_callable=AsyncMock,
            return_value=_make_mock_params(),
        ),
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "default",
                "messages": [{"role": "user", "content": "Hello"}],
                "chat_id": "my-test-session-01",
                "stream": False,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "Hello world!"


@pytest.mark.asyncio
async def test_completions_empty_chat_id_falls_back_to_default(
    client: AsyncClient, api_key: str
):
    """Empty chat_id is falsy and must fall back to a generated session, not 400."""
    with (
        patch(
            "app.api.openai_compat.completions.ai_agent_service_stream",
            new=_mock_agent_stream,
        ),
        patch(
            "app.api.openai_compat.completions._build_agent_params",
            new_callable=AsyncMock,
            return_value=_make_mock_params(),
        ),
    ):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "default",
                "messages": [{"role": "user", "content": "Hello"}],
                "chat_id": "",
                "stream": False,
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

    assert resp.status_code == 200
