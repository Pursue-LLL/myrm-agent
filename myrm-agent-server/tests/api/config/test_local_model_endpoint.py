"""Tests for the /test-local-model endpoint in the config router."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")
client = TestClient(app)

_URL = "/api/v1/config/test-local-model"
_PAYLOAD = {"model": "ollama/llama3", "base_url": "http://127.0.0.1:11434"}
_FACTORY = "myrm_agent_harness.toolkits.llms.create_litellm_model"
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
        patch("app.api.config.router._LOCAL_MODEL_TEST_TIMEOUT_S", 0.05),
    ):
        response = client.post(_URL, json=_PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["message"].startswith("No response within 0.05 seconds")
    assert "still be loading" in data["message"]
    assert state["cancelled"] is True


def test_provider_side_timeout_keeps_the_connection_message() -> None:
    """A timeout reported by the provider client is a connection problem, not a deadline expiry."""
    ainvoke = AsyncMock(side_effect=RuntimeError("litellm.Timeout: Connection timed out after 30 seconds"))
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
