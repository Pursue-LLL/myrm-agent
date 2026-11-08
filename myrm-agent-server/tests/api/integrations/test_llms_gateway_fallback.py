"""Tests for /integrations/llm/model-info lookups: gateway routes, spelling and candidates."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.llms.catalog import known_models, register_model, store

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="integrations")
_INFO = "/api/v1/integrations/llm/model-info"
_BATCH = "/api/v1/integrations/llm/model-info/batch"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with auth bypassed via loopback IP mock."""
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "_REGISTERED", {})


def _info(client: TestClient, model: str) -> dict[str, object]:
    response = client.post(_INFO, json={"model": model})
    assert response.status_code == 200
    return response.json()["data"]


def test_direct_hit_returns_the_capabilities(client: TestClient) -> None:
    data = _info(client, "gpt-4o")
    assert data["found"] is True
    assert data["capabilities"]["supports_vision"] is True


def test_a_gateway_composite_name_resolves_to_the_model_behind_it(client: TestClient) -> None:
    data = _info(client, "my-gateway/openai/gpt-4o")
    assert data["found"] is True
    assert data["capabilities"]["max_input_tokens"] == known_models()["gpt-4o"]["max_input_tokens"]


def test_the_spelling_of_the_name_does_not_matter(client: TestClient) -> None:
    key, entry = next(
        (name, info)
        for name, info in known_models().items()
        if name != name.lower() and isinstance(info.get("max_input_tokens"), int)
    )
    for spelled in (key, key.lower()):
        data = _info(client, spelled)
        assert data["found"] is True
        assert data["capabilities"]["max_input_tokens"] == entry["max_input_tokens"]


def test_the_capabilities_carry_no_legacy_max_tokens_field(client: TestClient) -> None:
    assert "max_tokens" not in _info(client, "gpt-4o")["capabilities"]


def test_an_unknown_model_is_not_found_and_its_batch_entry_has_empty_capabilities(client: TestClient) -> None:
    data = _info(client, "completely_non_existent_fake_model_xyz_999")
    assert data["found"] is False
    batch = client.post(_BATCH, json={"models": ["completely_non_existent_fake_model_xyz_999"]}).json()["data"]
    assert batch["completely_non_existent_fake_model_xyz_999"]["supports_vision"] is False


def test_a_registered_model_is_found_through_a_route_like_any_other(client: TestClient) -> None:
    register_model("zai/glm-test-vision", {"provider": "zai", "supports_vision": True, "max_input_tokens": 64_000})
    data = _info(client, "openrouter/zai/glm-test-vision")
    assert data["found"] is True
    assert data["capabilities"]["supports_vision"] is True
    assert data["capabilities"]["max_input_tokens"] == 64_000
