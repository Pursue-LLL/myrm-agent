"""Model probes resolve the WebUI subscription placeholder to the stored token, host-pinned.

The Models page validates and speed-tests with ``__myrm_oauth_token__`` as the api key when a
SuperGrok subscription backs the provider. The placeholder must become the real token on the
server before the request leaves, and the token must never go to a host it was not issued for.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.integrations.llms import _reachability_cache
from app.services.agent.provider_oauth_tokens import OAUTH_KEY_MARKER
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")

_LOAD_STORED = "app.services.agent.provider_oauth_tokens._load_stored_credential"
_GET_LLM = "myrm_agent_harness.toolkits.llms.llm_manager.get_llm"
_API = "/api/v1/integrations/llm"
_XAI_BASE_URL = "https://api.x.ai/v1"


def _stored_credential() -> dict[str, object]:
    return {"token": "stored-subscription-token", "base_url": _XAI_BASE_URL, "expires_at": time.time() + 3600}


def _llm_replying(content: str = "pong") -> AsyncMock:
    llm = AsyncMock()
    llm.ainvoke.return_value = type("Reply", (), {"content": content})()
    return llm


@pytest.fixture
def client() -> Iterator[TestClient]:
    _reachability_cache.clear()
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield TestClient(app)
    _reachability_cache.clear()


class TestVerify:
    def _verify(self, client: TestClient, **overrides: object) -> object:
        body = {"model": "xai/grok-4", "api_key": OAUTH_KEY_MARKER, "base_url": _XAI_BASE_URL, **overrides}
        return client.post(f"{_API}/verify", json=body)

    def test_stored_token_replaces_the_placeholder(self, client: TestClient) -> None:
        get_llm = AsyncMock(return_value=_llm_replying())

        with patch(_GET_LLM, get_llm), patch(_LOAD_STORED, AsyncMock(return_value=_stored_credential())):
            response = self._verify(client)

        assert response.status_code == 200
        assert get_llm.await_args.kwargs["api_key"] == "stored-subscription-token"
        assert get_llm.await_args.kwargs["base_url"] == _XAI_BASE_URL

    def test_foreign_host_never_receives_the_token(self, client: TestClient) -> None:
        get_llm = AsyncMock(return_value=_llm_replying())

        with patch(_GET_LLM, get_llm), patch(_LOAD_STORED, AsyncMock(return_value=_stored_credential())):
            response = self._verify(client, base_url="https://collector.example/v1")

        assert response.status_code == 502
        get_llm.assert_not_awaited()
        assert "stored-subscription-token" not in response.text

    def test_disconnected_subscription_fails_without_an_upstream_call(self, client: TestClient) -> None:
        get_llm = AsyncMock(return_value=_llm_replying())

        with patch(_GET_LLM, get_llm), patch(_LOAD_STORED, AsyncMock(return_value=None)):
            response = self._verify(client)

        assert response.status_code == 502
        get_llm.assert_not_awaited()

    def test_ordinary_keys_are_untouched(self, client: TestClient) -> None:
        get_llm = AsyncMock(return_value=_llm_replying())
        load_stored = AsyncMock()

        with patch(_GET_LLM, get_llm), patch(_LOAD_STORED, load_stored):
            response = self._verify(client, model="gpt-4o-mini", api_key="sk-user", base_url="https://api.openai.com/v1")

        assert response.status_code == 200
        assert get_llm.await_args.kwargs["api_key"] == "sk-user"
        load_stored.assert_not_awaited()


class TestCheckReachability:
    def _check(self, client: TestClient, **overrides: object) -> dict[str, object]:
        body = {"model": "xai/grok-4", "api_key": OAUTH_KEY_MARKER, "base_url": _XAI_BASE_URL, **overrides}
        return client.post(f"{_API}/check-reachability", json=body).json()["data"]

    def test_stored_token_replaces_the_placeholder(self, client: TestClient) -> None:
        get_llm = AsyncMock(return_value=MagicMock())
        health_check = "myrm_agent_harness.toolkits.llms.fallback.health_check.lightweight_health_check"

        with (
            patch(_GET_LLM, get_llm),
            patch(health_check, AsyncMock(return_value=True)),
            patch(_LOAD_STORED, AsyncMock(return_value=_stored_credential())),
        ):
            data = self._check(client)

        assert data["reachable"] is True
        assert get_llm.await_args.kwargs["api_key"] == "stored-subscription-token"

    def test_foreign_host_is_reported_unreachable_without_an_upstream_call(self, client: TestClient) -> None:
        get_llm = AsyncMock(return_value=MagicMock())

        with patch(_GET_LLM, get_llm), patch(_LOAD_STORED, AsyncMock(return_value=_stored_credential())):
            data = self._check(client, base_url="https://collector.example/v1")

        assert data["reachable"] is False
        get_llm.assert_not_awaited()
        assert "stored-subscription-token" not in str(data)


class TestSpeedTest:
    def test_each_model_resolves_its_own_credential(self, client: TestClient) -> None:
        async def stream(messages: object, config: object = None) -> object:
            yield type("Chunk", (), {"content": "1"})()

        llm = MagicMock()
        llm.astream = stream
        get_llm = AsyncMock(return_value=llm)

        with patch(_GET_LLM, get_llm), patch(_LOAD_STORED, AsyncMock(return_value=_stored_credential())):
            response = client.post(
                f"{_API}/speed-test",
                json={
                    "models": [
                        {"model": "xai/grok-4", "api_key": OAUTH_KEY_MARKER, "base_url": _XAI_BASE_URL},
                        {"model": "xai/grok-4", "api_key": OAUTH_KEY_MARKER, "base_url": "https://collector.example/v1"},
                        {"model": "gpt-4o-mini", "api_key": "sk-user", "base_url": "https://api.openai.com/v1"},
                    ]
                },
            )

        assert response.status_code == 200
        outcomes = {(item["model"], item["status"]) for item in response.json()["data"]}
        assert outcomes == {("xai/grok-4", "ok"), ("xai/grok-4", "error"), ("gpt-4o-mini", "ok")}
        sent_keys = sorted(call.kwargs["api_key"] for call in get_llm.await_args_list)
        assert sent_keys == ["sk-user", "stored-subscription-token"]
