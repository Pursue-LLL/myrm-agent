"""Tests for GET /api/v1/health/info capability detection.

The desktop shell asks for this route while the first screen is loading and the handler runs on the event loop, so
answering it must not import optional packages or start the tokenizer (see ``_is_installed`` in the router).
"""

from __future__ import annotations

import importlib.util
import sys
import types

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.retriever.bm25 import TokenizerService

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")

# The route reports whether each optional package is installed ...
_FLAG_BY_PACKAGE = {
    "faster_whisper": "local_stt_available",
    "edge_tts": "edge_tts_available",
    "piper": "local_tts_available",
}
# ... and these are the packages whose import made the first call slow (faster-whisper pulls in ctranslate2 and PyAV).
_HEAVY_PACKAGES = (*_FLAG_BY_PACKAGE, "jieba", "ctranslate2", "av")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_system_info_returns_capabilities_booleans(client: TestClient) -> None:
    response = client.get("/api/v1/health/info")
    assert response.status_code == 200

    body = response.json()
    assert "deploy_mode" in body
    assert "server_version" in body
    assert isinstance(body["server_version"], str)
    assert "harness_version" in body
    assert isinstance(body["harness_version"], str)

    # Assert newly added capability check indicators are returned and typed correctly
    assert "local_stt_available" in body
    assert isinstance(body["local_stt_available"], bool)
    assert "edge_tts_available" in body
    assert isinstance(body["edge_tts_available"], bool)
    assert "local_tts_available" in body
    assert isinstance(body["local_tts_available"], bool)
    assert body.get("data_region") == "local"


def test_system_info_returns_custom_data_region(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_DATA_REGION", "nrt")
    response = client.get("/api/v1/health/info")
    assert response.status_code == 200
    body = response.json()
    assert body.get("data_region") == "nrt"


def _loaded_heavy_modules() -> list[str]:
    return sorted(name for name in sys.modules if name.split(".")[0] in _HEAVY_PACKAGES)


def test_system_info_loads_no_optional_package_and_leaves_the_tokenizer_alone(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_: TokenizerService) -> str:
        raise AssertionError("/health/info must not start the tokenizer")

    monkeypatch.setattr(TokenizerService, "backend", property(refuse))
    for name in _loaded_heavy_modules():
        monkeypatch.delitem(sys.modules, name)

    response = client.get("/api/v1/health/info")

    assert response.status_code == 200
    assert _loaded_heavy_modules() == []


@pytest.mark.parametrize(
    "installed",
    [
        set(),
        {"faster_whisper"},
        {"edge_tts"},
        {"piper"},
        set(_FLAG_BY_PACKAGE),
    ],
    ids=["none", "stt-only", "edge-only", "piper-only", "all"],
)
def test_each_flag_follows_its_own_package(client: TestClient, monkeypatch: pytest.MonkeyPatch, installed: set[str]) -> None:
    find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, package: str | None = None) -> object | None:
        if name in _FLAG_BY_PACKAGE:
            return object() if name in installed else None
        return find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    body = client.get("/api/v1/health/info").json()

    assert {flag: body[flag] for flag in _FLAG_BY_PACKAGE.values()} == {
        flag: package in installed for package, flag in _FLAG_BY_PACKAGE.items()
    }


def test_a_module_loaded_without_a_spec_counts_as_installed_and_a_blocked_one_does_not(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", types.ModuleType("faster_whisper"))
    monkeypatch.setitem(sys.modules, "edge_tts", None)

    response = client.get("/api/v1/health/info")

    assert response.status_code == 200
    body = response.json()
    assert body["local_stt_available"] is True
    assert body["edge_tts_available"] is False
