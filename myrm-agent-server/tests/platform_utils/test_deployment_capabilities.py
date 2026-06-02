"""Tests for deployment capability registry."""

from __future__ import annotations

import pytest

from app.platform_utils.deployment_capabilities import (
    _reset_capabilities_cache_for_testing,
    get_deployment_capabilities,
)


@pytest.fixture(autouse=True)
def _clear_caps_cache() -> None:
    from app.config.deploy_mode import get_deploy_mode

    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()
    yield
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def test_local_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_MODE", "local")
    caps = get_deployment_capabilities()
    assert caps.allows_local_skills is True
    assert caps.is_sandbox_instance is False
    assert caps.uses_platform_budget is False
    assert caps.default_metrics_enabled is False


def test_sandbox_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    caps = get_deployment_capabilities()
    assert caps.allows_local_skills is False
    assert caps.is_sandbox_instance is True
    assert caps.uses_platform_budget is True
    assert caps.validates_mcp_response_size is True
    assert caps.runs_sandbox_startup_validation is True


def test_tauri_treated_as_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_MODE", "tauri")
    caps = get_deployment_capabilities()
    assert caps.allows_local_skills is True
    assert caps.is_sandbox_instance is False
