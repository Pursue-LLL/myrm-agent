"""Tests for the /test-local-model endpoint in the config router."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.config.routes.diagnostics import _classify_local_model_error
from tests.support.fake_chat_provider import fake_chat_provider
from tests.support.fake_retrieval_provider import unreachable_api_base
from tests.support.minimal_app import build_minimal_app
from tests.support.provider_failures import provider_failure

app = build_minimal_app(preset="config")
client = TestClient(app)

_URL = "/api/v1/config/test-local-model"
_PAYLOAD = {"model": "ollama/llama3", "base_url": "http://127.0.0.1:11434"}
_FACTORY = "myrm_agent_harness.toolkits.llms.create_chat_model"
# Far above the patched deadline, yet bounded so a missing deadline fails fast instead of hanging.
_STALL_S = 5.0


def _llm_with(ainvoke: AsyncMock) -> MagicMock:
    llm = MagicMock()
    llm.ainvoke = ainvoke
    return llm


def test_reachable_model_reports_success() -> None:
    """A model that answers is reported as reachable with its latency."""
    ainvoke = AsyncMock(return_value=MagicMock())
    with patch(_FACTORY, return_value=_llm_with(ainvoke)):
        response = client.post(_URL, json=_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "OK"
    assert isinstance(data["latency_ms"], int)
    ainvoke.assert_awaited_once()
    assert ainvoke.await_args is not None
    # Per-call limits are enforced by the endpoint deadline; config kwargs never reach the provider.
    assert "config" not in ainvoke.await_args.kwargs


def test_stalled_model_is_cancelled_and_reported_as_no_response() -> None:
    """A model that never answers is abandoned at the deadline and reported as silent, not as unreachable."""
    state = {"cancelled": False}

    async def _stall(*_args: object, **_kwargs: object) -> None:
        try:
            await asyncio.sleep(_STALL_S)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    with (
        patch(_FACTORY, return_value=_llm_with(AsyncMock(side_effect=_stall))),
        patch("app.api.config.routes.diagnostics._LOCAL_MODEL_TEST_TIMEOUT_S", 0.05),
    ):
        response = client.post(_URL, json=_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["message"].startswith("No response within 0.05 seconds")
    assert "still be loading" in data["message"]
    assert state["cancelled"] is True


def test_provider_side_timeout_keeps_the_connection_message() -> None:
    """A timeout reported by the HTTP client is a connection problem, not a deadline expiry."""
    ainvoke = AsyncMock(side_effect=httpx.ConnectTimeout("Connection timed out after 30 seconds"))
    with patch(_FACTORY, return_value=_llm_with(ainvoke)):
        response = client.post(_URL, json=_PAYLOAD)

    assert response.json()["message"] == "Connection timed out — check the server address"


def test_provider_failure_is_classified() -> None:
    """A provider error is mapped to a user-facing message instead of leaking the raw exception."""
    ainvoke = AsyncMock(side_effect=ConnectionRefusedError("[Errno 61] Connection refused"))
    with patch(_FACTORY, return_value=_llm_with(ainvoke)):
        response = client.post(_URL, json=_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "refused" in data["message"].lower()
    assert "Errno" not in data["message"]


def test_an_address_that_answers_with_another_apis_reply_is_not_a_reachable_model() -> None:
    """A mistyped address that lands on an OpenAI-compatible server answers 200 with JSON, which is no Ollama reply."""
    with fake_chat_provider("sk-right") as provider:
        response = client.post(_URL, json={"model": "ollama/llama3", "base_url": provider.base_url, "api_key": "sk-right"})

    assert response.json()["success"] is False
    # The server was reached and answered: what failed is the answer, not the connection.
    assert provider.requests


def test_a_wrong_key_is_judged_by_the_provider_after_the_right_key_was_accepted() -> None:
    """The real chat model asks the provider on every test; an answer given to the right key does not vouch for another."""
    with fake_chat_provider("sk-right") as provider:
        endpoint = {"model": "openai/test-chat", "base_url": provider.base_url}
        right = client.post(_URL, json={**endpoint, "api_key": "sk-right"}).json()
        wrong = client.post(_URL, json={**endpoint, "api_key": "sk-wrong"}).json()

    assert right["success"] is True
    assert (wrong["success"], wrong["message"]) == (False, "Authentication failed — check your API key")
    assert [seen.authorization for seen in provider.requests] == ["Bearer sk-right", "Bearer sk-wrong"]


def test_a_server_nothing_listens_on_is_reported_as_not_running() -> None:
    """The real chat model's failure to connect carries no "refused" wording, yet the message still says what to check."""
    response = client.post(_URL, json={"model": "ollama/llama3", "base_url": unreachable_api_base().removesuffix("/v1")})

    data = response.json()
    assert data["success"] is False
    assert data["message"].endswith("is the model server running?")
    assert "Errno" not in data["message"]


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (httpx.ConnectError("All connection attempts failed"), "Could not connect — is the model server running?"),
        (httpx.ConnectError("[Errno 61] Connection refused"), "Connection refused — is the model server running?"),
        (
            httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known"),
            "DNS resolution failed — check the base URL",
        ),
        (httpx.ConnectError("[Errno -2] Name or service not known"), "DNS resolution failed — check the base URL"),
        (
            httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"),
            "SSL/TLS error — check your server's certificate",
        ),
        (provider_failure(401, "Incorrect API key provided"), "Authentication failed — check your API key"),
        (provider_failure(404, "The model does not exist"), "Model not found — check the model name"),
        (provider_failure(500, "The server had an error"), "Connection test failed"),
    ],
    ids=["connect", "refused", "dns-macos", "dns-linux", "tls", "auth", "unknown-model", "server-fault"],
)
def test_each_failure_the_model_transport_raises_has_its_own_message(failure: Exception, message: str) -> None:
    assert _classify_local_model_error(failure) == message
