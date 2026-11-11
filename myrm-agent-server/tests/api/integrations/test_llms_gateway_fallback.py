"""Tests for /integrations/llm/model-info/batch lookups: gateway routes, spelling and registrations."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.llms.catalog import known_models, register_model, store

from app.api.integrations.llms import ModelCapabilities
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
_BATCH = "/api/v1/integrations/llm/model-info/batch"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_REGISTERED", {})


def _capabilities(client: TestClient, model: str) -> dict[str, object]:
    response = client.post(_BATCH, json={"models": [model]})
    assert response.status_code == 200
    return response.json()["data"][model]


def test_direct_hit_returns_the_capabilities(client: TestClient) -> None:
    assert _capabilities(client, "gpt-4o")["supports_vision"] is True


def test_a_gateway_composite_name_resolves_to_the_model_behind_it(client: TestClient) -> None:
    capabilities = _capabilities(client, "my-gateway/openai/gpt-4o")
    assert capabilities["supports_vision"] is True
    assert capabilities["max_input_tokens"] == known_models()["gpt-4o"]["max_input_tokens"]


def test_the_spelling_of_the_name_does_not_matter(client: TestClient) -> None:
    key, entry = next(
        (name, info)
        for name, info in known_models().items()
        if name != name.lower() and isinstance(info.get("max_input_tokens"), int)
    )
    for spelled in (key, key.lower()):
        assert _capabilities(client, spelled)["max_input_tokens"] == entry["max_input_tokens"]


def test_the_capabilities_carry_no_legacy_max_tokens_field(client: TestClient) -> None:
    assert "max_tokens" not in _capabilities(client, "gpt-4o")


def test_an_unknown_model_gets_empty_capabilities(client: TestClient) -> None:
    assert _capabilities(client, "completely_non_existent_fake_model_xyz_999") == ModelCapabilities().model_dump()


def test_a_registered_model_resolves_through_a_gateway_route(client: TestClient) -> None:
    register_model("zai/glm-test-vision", {"provider": "zai", "supports_vision": True, "max_input_tokens": 64_000})
    capabilities = _capabilities(client, "openrouter/zai/glm-test-vision")
    assert capabilities["supports_vision"] is True
    assert capabilities["max_input_tokens"] == 64_000
