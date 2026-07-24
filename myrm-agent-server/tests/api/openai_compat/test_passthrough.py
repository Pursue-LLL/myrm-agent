"""Unit tests for LLM passthrough module.

Tests _resolve_passthrough_provider, is_passthrough_model,
_build_litellm_kwargs, passthrough_stream, and passthrough_completion.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.openai_compat.passthrough import (
    _build_litellm_kwargs,
    _resolve_passthrough_provider,
    is_passthrough_model,
    passthrough_completion,
    passthrough_stream,
)
from app.api.openai_compat.types import (
    ChatCompletionRequest,
    ChatMessage,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="openai_compat_only", openai_compat=True)
_MOCK_PROVIDERS_DICT: dict[str, object] = {
    "providers": [
        {
            "id": "anthropic",
            "isEnabled": True,
            "providerType": "anthropic",
            "apiKeys": [{"key": "sk-ant-test-xxx", "isActive": True}],
            "enabledModels": ["claude-sonnet-4-20250514", "claude-3-haiku"],
            "apiUrl": "",
        },
        {
            "id": "openai",
            "isEnabled": True,
            "providerType": "",
            "apiKeys": [{"key": "sk-test-xxx", "isActive": True}],
            "enabledModels": ["gpt-4o-mini", "gpt-4o"],
            "apiUrl": "",
        },
        {
            "id": "deepseek",
            "isEnabled": True,
            "providerType": "deepseek",
            "apiKeys": [{"key": "sk-ds-test", "isActive": True}],
            "enabledModels": ["deepseek-chat"],
            "apiUrl": "https://api.deepseek.com/v1",
        },
        {
            "id": "disabled-provider",
            "isEnabled": False,
            "providerType": "",
            "apiKeys": [{"key": "sk-disabled", "isActive": True}],
            "enabledModels": ["disabled-model"],
        },
        {
            "id": "no-keys-provider",
            "isEnabled": True,
            "providerType": "",
            "apiKeys": [],
            "enabledModels": ["orphan-model"],
        },
    ]
}


class TestResolvePassthroughProvider:
    """Tests for _resolve_passthrough_provider."""

    def test_bare_anthropic_model(self):
        litellm_model, all_keys, base_url, pid = _resolve_passthrough_provider("claude-sonnet-4-20250514", _MOCK_PROVIDERS_DICT)
        assert "anthropic" in litellm_model.lower()
        assert "claude-sonnet-4-20250514" in litellm_model
        assert "sk-ant-test-xxx" in all_keys
        assert base_url is None
        assert pid == "anthropic"

    def test_bare_openai_model(self):
        litellm_model, all_keys, _, _pid = _resolve_passthrough_provider("gpt-4o-mini", _MOCK_PROVIDERS_DICT)
        assert "gpt-4o-mini" in litellm_model
        assert "sk-test-xxx" in all_keys

    def test_bare_deepseek_model(self):
        litellm_model, all_keys, base_url, _pid = _resolve_passthrough_provider("deepseek-chat", _MOCK_PROVIDERS_DICT)
        assert "deepseek" in litellm_model.lower()
        assert "sk-ds-test" in all_keys
        assert base_url == "https://api.deepseek.com/v1"

    def test_prefixed_model(self):
        litellm_model, all_keys, _, _pid = _resolve_passthrough_provider("anthropic/claude-3-haiku", _MOCK_PROVIDERS_DICT)
        assert "anthropic" in litellm_model.lower()
        assert "claude-3-haiku" in litellm_model
        assert "sk-ant-test-xxx" in all_keys

    def test_case_insensitive_match(self):
        litellm_model, _, _, _ = _resolve_passthrough_provider("Claude-Sonnet-4-20250514", _MOCK_PROVIDERS_DICT)
        assert "claude-sonnet-4-20250514" in litellm_model.lower()

    def test_nonexistent_model_raises(self):
        with pytest.raises(ValueError, match="not found"):
            _resolve_passthrough_provider("nonexistent-model", _MOCK_PROVIDERS_DICT)

    def test_disabled_provider_skipped(self):
        with pytest.raises(ValueError, match="not found"):
            _resolve_passthrough_provider("disabled-model", _MOCK_PROVIDERS_DICT)

    def test_no_active_keys_skipped(self):
        with pytest.raises(ValueError, match="not found"):
            _resolve_passthrough_provider("orphan-model", _MOCK_PROVIDERS_DICT)

    def test_empty_providers_raises(self):
        with pytest.raises(ValueError, match="No providers configured"):
            _resolve_passthrough_provider("any-model", {"providers": "not-a-list"})


class TestIsPassthroughModel:
    """Tests for is_passthrough_model."""

    @pytest.mark.asyncio
    async def test_disabled_proxy_returns_false(self):
        with patch(
            "app.api.openai_compat.passthrough._is_proxy_enabled",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await is_passthrough_model("gpt-4o-mini")
        assert result is False

    @pytest.mark.asyncio
    async def test_agent_alias_returns_false(self):
        with patch(
            "app.api.openai_compat.passthrough._is_proxy_enabled",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await is_passthrough_model("default")
        assert result is False

    @pytest.mark.asyncio
    async def test_configured_model_returns_true(self):
        with (
            patch(
                "app.api.openai_compat.passthrough._is_proxy_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.passthrough._is_agent_id",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.api.openai_compat.passthrough._load_providers_dict",
                new_callable=AsyncMock,
                return_value=_MOCK_PROVIDERS_DICT,
            ),
        ):
            result = await is_passthrough_model("claude-sonnet-4-20250514")
        assert result is True

    @pytest.mark.asyncio
    async def test_unknown_model_returns_false(self):
        with (
            patch(
                "app.api.openai_compat.passthrough._is_proxy_enabled",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.passthrough._is_agent_id",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.api.openai_compat.passthrough._load_providers_dict",
                new_callable=AsyncMock,
                return_value=_MOCK_PROVIDERS_DICT,
            ),
        ):
            result = await is_passthrough_model("unknown-model-xyz")
        assert result is False


def _make_request(
    model: str = "claude-sonnet-4-20250514",
    content: str = "hello",
    **kwargs: object,
) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model=model,
        messages=[ChatMessage(role="user", content=content)],
        **kwargs,
    )


class TestBuildLitellmKwargs:
    """Tests for _build_litellm_kwargs with explicit credential arguments."""

    @pytest.mark.asyncio
    async def test_basic_kwargs(self):
        kwargs = await _build_litellm_kwargs(
            _make_request(),
            litellm_model="anthropic/claude-sonnet-4-20250514",
            api_key="sk-ant-test-xxx",
            base_url=None,
            stream=False,
        )

        assert "anthropic" in kwargs["model"]
        assert kwargs["api_key"] == "sk-ant-test-xxx"
        assert kwargs["stream"] is False
        assert len(kwargs["messages"]) == 1

    @pytest.mark.asyncio
    async def test_optional_params_passed(self):
        kwargs = await _build_litellm_kwargs(
            _make_request(temperature=0.7, max_tokens=100, top_p=0.9),
            litellm_model="anthropic/claude-sonnet-4-20250514",
            api_key="sk-ant-test-xxx",
            base_url=None,
            stream=True,
        )

        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 100
        assert kwargs["top_p"] == 0.9
        assert kwargs["stream"] is True

    @pytest.mark.asyncio
    async def test_base_url_included(self):
        kwargs = await _build_litellm_kwargs(
            _make_request(model="deepseek-chat"),
            litellm_model="deepseek/deepseek-chat",
            api_key="sk-ds-test",
            base_url="https://api.deepseek.com/v1",
            stream=False,
        )

        assert kwargs["api_base"] == "https://api.deepseek.com/v1"


def _mock_litellm_response(content: str = "Hello!") -> SimpleNamespace:
    """Create a mock litellm non-streaming response."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


async def _mock_litellm_stream():
    """Create a mock litellm streaming async generator."""
    yield SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content="Hi"),
                finish_reason=None,
            )
        ]
    )
    yield SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=" there"),
                finish_reason=None,
            )
        ]
    )
    yield SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=None),
                finish_reason="stop",
            )
        ]
    )


class TestPassthroughCompletion:
    """Tests for passthrough_completion function."""

    @pytest.mark.asyncio
    async def test_success(self):
        with (
            patch(
                "app.api.openai_compat.passthrough._build_litellm_kwargs",
                new_callable=AsyncMock,
                return_value={"model": "anthropic/claude-sonnet-4-20250514", "messages": [], "api_key": "k", "stream": False},
            ),
            patch(
                "litellm.acompletion",
                new_callable=AsyncMock,
                return_value=_mock_litellm_response("Test response"),
            ),
        ):
            resp = await passthrough_completion(_make_request())

        assert resp.choices[0].message.content == "Test response"
        assert resp.usage.total_tokens == 15

    @pytest.mark.asyncio
    async def test_upstream_error_raises_502(self):
        from fastapi import HTTPException

        with (
            patch(
                "app.api.openai_compat.passthrough._build_litellm_kwargs",
                new_callable=AsyncMock,
                return_value={"model": "x", "messages": [], "api_key": "k", "stream": False},
            ),
            patch(
                "litellm.acompletion",
                new_callable=AsyncMock,
                side_effect=RuntimeError("connection refused"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await passthrough_completion(_make_request())
            assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_config_error_raises_422(self):
        from fastapi import HTTPException

        with patch(
            "app.api.openai_compat.passthrough._build_litellm_kwargs",
            new_callable=AsyncMock,
            side_effect=ValueError("No providers"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await passthrough_completion(_make_request())
            assert exc_info.value.status_code == 422


class TestPassthroughStream:
    """Tests for passthrough_stream function."""

    @pytest.mark.asyncio
    async def test_success_yields_sse(self):
        with (
            patch(
                "app.api.openai_compat.passthrough._build_litellm_kwargs",
                new_callable=AsyncMock,
                return_value={"model": "anthropic/claude-sonnet-4-20250514", "messages": [], "api_key": "k", "stream": True},
            ),
            patch(
                "litellm.acompletion",
                new_callable=AsyncMock,
                return_value=_mock_litellm_stream(),
            ),
        ):
            chunks: list[str] = []
            async for chunk in passthrough_stream(_make_request()):
                chunks.append(chunk)

        assert any("[DONE]" in c for c in chunks)
        content_chunks = [c for c in chunks if "content" in c and "Hi" in c]
        assert len(content_chunks) >= 1

    @pytest.mark.asyncio
    async def test_config_error_yields_error_sse(self):
        with patch(
            "app.api.openai_compat.passthrough._build_litellm_kwargs",
            new_callable=AsyncMock,
            side_effect=ValueError("No providers"),
        ):
            chunks: list[str] = []
            async for chunk in passthrough_stream(_make_request()):
                chunks.append(chunk)

        assert len(chunks) == 2
        error_data = json.loads(chunks[0].replace("data: ", ""))
        assert error_data["error"]["type"] == "configuration_error"
        assert chunks[1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_upstream_error_yields_error_sse(self):
        with (
            patch(
                "app.api.openai_compat.passthrough._build_litellm_kwargs",
                new_callable=AsyncMock,
                return_value={"model": "x", "messages": [], "api_key": "k", "stream": True},
            ),
            patch(
                "litellm.acompletion",
                new_callable=AsyncMock,
                side_effect=RuntimeError("network error"),
            ),
        ):
            chunks: list[str] = []
            async for chunk in passthrough_stream(_make_request()):
                chunks.append(chunk)

        error_chunks = [c for c in chunks if "upstream_error" in c]
        assert len(error_chunks) == 1
        assert any("[DONE]" in c for c in chunks)


class TestPassthroughHTTP:
    """HTTP-level tests for passthrough routing in completions endpoint."""

    @pytest.fixture
    async def client(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    @pytest.fixture
    async def api_key(self, client: AsyncClient) -> str:
        resp = await client.post("/api/v1/api-keys", json={"name": "Passthrough Test"})
        return resp.json()["key"]

    @pytest.mark.asyncio
    async def test_passthrough_non_streaming_config_error(
        self,
        client: AsyncClient,
        api_key: str,
    ):
        """When _build_litellm_kwargs raises ValueError, return 422."""
        with (
            patch(
                "app.api.openai_compat.passthrough.is_passthrough_model",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.passthrough._build_litellm_kwargs",
                new_callable=AsyncMock,
                side_effect=ValueError("Model 'bad-model' not found"),
            ),
        ):
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "bad-model",
                    "messages": [{"role": "user", "content": "test"}],
                    "stream": False,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )

        assert resp.status_code == 422
        data = resp.json()
        assert data["detail"]["error"]["type"] == "configuration_error"

    @pytest.mark.asyncio
    async def test_passthrough_streaming_config_error(
        self,
        client: AsyncClient,
        api_key: str,
    ):
        """When _build_litellm_kwargs raises ValueError in stream, return SSE error."""
        with (
            patch(
                "app.api.openai_compat.passthrough.is_passthrough_model",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.openai_compat.passthrough._build_litellm_kwargs",
                new_callable=AsyncMock,
                side_effect=ValueError("Model 'bad-model' not found"),
            ),
        ):
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "bad-model",
                    "messages": [{"role": "user", "content": "test"}],
                    "stream": True,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        lines = resp.text.strip().split("\n\n")
        error_data = json.loads(lines[0].replace("data: ", ""))
        assert error_data["error"]["type"] == "configuration_error"
        assert lines[-1] == "data: [DONE]"
