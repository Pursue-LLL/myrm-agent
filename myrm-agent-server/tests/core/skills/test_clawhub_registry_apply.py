"""Unit tests for ClawHub registry apply SSOT (user config overrides legacy env)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.skills.market.sources.clawhub_registry import (
    CLAWHUB_DEFAULT_URL,
    CLAWHUB_REGISTRY_ENV,
    CLAWHUB_URL_ENV,
    resolve_registry_base_url,
)

from app.core.skills.clawhub_registry import apply_clawhub_registry_url


@pytest.fixture(autouse=True)
def _clear_registry_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CLAWHUB_URL_ENV, raising=False)
    monkeypatch.delenv(CLAWHUB_REGISTRY_ENV, raising=False)
    monkeypatch.delenv("OPENCLAW_CLAWHUB_URL", raising=False)


@patch("app.core.skills.market_service.market_service.refresh_clawhub_source")
def test_apply_intl_clears_shadow_registry_env(
    _refresh: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLAWHUB_REGISTRY_ENV, "https://skill.xfyun.cn")
    effective = apply_clawhub_registry_url("")

    assert effective == CLAWHUB_DEFAULT_URL
    assert os.environ.get(CLAWHUB_URL_ENV) == CLAWHUB_DEFAULT_URL
    assert CLAWHUB_REGISTRY_ENV not in os.environ
    assert resolve_registry_base_url() == CLAWHUB_DEFAULT_URL


@patch("app.core.skills.market_service.market_service.refresh_clawhub_source")
def test_apply_cn_sets_clawhub_url_and_clears_shadow_env(
    _refresh: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CLAWHUB_REGISTRY_ENV, "https://registry.example.com")
    effective = apply_clawhub_registry_url("https://skill.xfyun.cn")

    assert effective == "https://skill.xfyun.cn"
    assert os.environ.get(CLAWHUB_URL_ENV) == "https://skill.xfyun.cn"
    assert CLAWHUB_REGISTRY_ENV not in os.environ
    assert resolve_registry_base_url() == "https://skill.xfyun.cn"
