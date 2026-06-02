"""Tests for preflight WebUI model warning."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.config import ConfigIncompleteError

from app.config.deploy_mode import get_deploy_mode
from app.config.pre_flight import preflight_check_config
from app.core.types import ModelConfig


def _clear_deploy_mode_cache() -> None:
    get_deploy_mode.cache_clear()


@pytest.mark.parametrize("deploy_mode", ["local", "tauri"])
def test_preflight_warns_when_webui_model_missing(deploy_mode: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_deploy_mode_cache()
    monkeypatch.setenv("DEPLOY_MODE", deploy_mode)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with patch(
        "app.services.agent.platform_config.webui_model_preflight_warning",
        return_value="WebUI default model is not configured (Settings > Model Service)",
    ):
        result = preflight_check_config()

    assert any("WebUI default model" in w for w in result.warnings)


def test_webui_preflight_skipped_under_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_deploy_mode_cache()
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_webui_preflight_skipped_under_pytest")

    from app.services.agent.platform_config import webui_model_preflight_warning

    assert webui_model_preflight_warning() is None


def test_webui_preflight_skipped_in_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_deploy_mode_cache()
    monkeypatch.setenv("DEPLOY_MODE", "sandbox")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    from app.services.agent.platform_config import webui_model_preflight_warning

    assert webui_model_preflight_warning() is None


def test_webui_preflight_warns_when_db_not_initialized(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_deploy_mode_cache()
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with patch("app.services.agent.platform_config._user_config_table_exists", return_value=False):
        from app.services.agent.platform_config import webui_model_preflight_warning

        warning = webui_model_preflight_warning()

    assert warning is not None
    assert "database not initialized" in warning


def test_webui_preflight_returns_warning_on_config_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_deploy_mode_cache()
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    async def _raise_incomplete() -> ModelConfig:
        raise ConfigIncompleteError(
            user_friendly_message={"en": "No providers configured"},
            technical_details="test",
            resolution_steps=[],
            error_code="provider_not_configured",
        )

    with patch("app.services.agent.platform_config._user_config_table_exists", return_value=True):
        with patch(
            "app.services.agent.platform_config.load_platform_model_config",
            side_effect=_raise_incomplete,
        ):
            from app.services.agent.platform_config import webui_model_preflight_warning

            warning = webui_model_preflight_warning()

    assert warning is not None
    assert "No providers configured" in warning
    assert "Settings > Model Service" in warning
