"""POST /security/generate-policy: the request it makes to the model and what it answers when that goes wrong.

The model's answer is a fixed text; the policy parser, validator and explainer run for real.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="security")

_GATEWAY = "http://gateway.test/v1"
_POLICY = '{"permissions": {"shell_exec": "deny"}, "networkAllowlist": ["github.com"]}'
_SAVED_PROVIDERS = {
    "providers": [{"id": "openai", "isEnabled": True, "apiUrl": _GATEWAY, "apiKeys": [{"key": "sk-test", "isActive": True}]}],
    "defaultModelConfig": {"baseModel": {"primary": {"providerId": "openai", "model": "gpt-4o-mini"}}},
}
_ASK = "app.api.security.generate.acomplete_text"
_LOAD_CONFIGS = "app.core.channel_bridge.config_loader.load_user_configs"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def saved_settings() -> Iterator[None]:
    """One enabled provider with a key, and a default model on it, as the settings page stores them."""
    with patch(_LOAD_CONFIGS, AsyncMock(return_value=SimpleNamespace(providers_dict=_SAVED_PROVIDERS))):
        yield


def _draft(client: TestClient, **extra: object) -> httpx.Response:
    return client.post("/api/v1/security/generate-policy", json={"text": "deny shell commands", **extra})


def test_the_default_model_drafts_the_policy(client: TestClient, saved_settings: None) -> None:
    with patch(_ASK, AsyncMock(return_value=_POLICY)) as ask:
        response = _draft(client)

    assert response.status_code == 200
    body = response.json()
    assert body["generated_config"] == {"permissions": {"shell_exec": "deny"}, "networkAllowlist": ["github.com"]}
    assert body["explanation_en"] and body["explanation_zh"]
    model, messages = ask.await_args.args
    assert model == "openai/gpt-4o-mini"
    assert messages[-1]["content"] == "deny shell commands"
    assert ask.await_args.kwargs == {
        "api_key": "sk-test",
        "api_base": _GATEWAY,
        "temperature": 0.1,
        "max_tokens": 1500,
        "timeout": 30,
    }


def test_a_selected_model_is_asked_through_the_default_providers_credentials(client: TestClient, saved_settings: None) -> None:
    with patch(_ASK, AsyncMock(return_value=_POLICY)) as ask:
        response = _draft(client, model_selection={"providerId": "openai", "model": "gpt-4.1"})

    assert response.status_code == 200
    assert ask.await_args.args[0] == "openai/gpt-4.1"
    assert ask.await_args.kwargs["api_key"] == "sk-test"
    assert ask.await_args.kwargs["api_base"] == _GATEWAY


def test_a_model_that_cannot_be_reached_is_a_502(client: TestClient, saved_settings: None) -> None:
    with patch(_ASK, AsyncMock(side_effect=RuntimeError("connection refused"))):
        response = _draft(client)

    assert response.status_code == 502
    assert response.json()["detail"] == "LLM call failed"


def test_an_answer_that_is_not_a_policy_is_a_422(client: TestClient, saved_settings: None) -> None:
    with patch(_ASK, AsyncMock(return_value="I cannot help with that.")):
        response = _draft(client)

    assert response.status_code == 422
    assert response.json()["detail"] == "Failed to parse LLM response"


def test_without_a_default_model_the_model_is_not_asked(client: TestClient) -> None:
    with (
        patch(_LOAD_CONFIGS, AsyncMock(return_value=SimpleNamespace(providers_dict={}))),
        patch(_ASK, AsyncMock()) as ask,
    ):
        response = _draft(client)

    assert response.status_code == 400
    ask.assert_not_awaited()
