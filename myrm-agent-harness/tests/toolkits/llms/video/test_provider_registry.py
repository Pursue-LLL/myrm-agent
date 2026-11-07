"""Tests for the built-in video provider registry.

[POS]
Unit tests for get_registry: every built-in provider is registered through its ``module:Class``
reference, and a provider whose import fails is skipped without taking the others down.
"""

from __future__ import annotations

import importlib
import logging
from types import ModuleType

import pytest

from myrm_agent_harness.toolkits.llms.video.providers import registry as registry_module

_EXPECTED_IDS = {"openai", "gemini", "qwen", "minimax", "xai", "fal", "volcengine"}


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry_module, "_registry", None)


def _registered_ids() -> set[str]:
    return {str(info["id"]) for info in registry_module.get_registry().list_providers()}


def test_every_builtin_provider_is_registered() -> None:
    assert _registered_ids() == _EXPECTED_IDS


def test_registry_is_created_once() -> None:
    assert registry_module.get_registry() is registry_module.get_registry()


def test_provider_that_fails_to_import_is_skipped_and_reported(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    real_import = importlib.import_module

    def import_module(name: str, package: str | None = None) -> ModuleType:
        if name.endswith(".fal_provider"):
            raise ImportError("optional dependency missing")
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", import_module)
    with caplog.at_level(logging.WARNING, logger=registry_module.logger.name):
        assert _registered_ids() == _EXPECTED_IDS - {"fal"}
    assert "FalVideoProvider" in caplog.text
