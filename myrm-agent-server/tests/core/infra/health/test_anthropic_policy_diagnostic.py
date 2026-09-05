"""Unit tests for AnthropicSubscriptionPolicyDiagnostic."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.infra.health.server_diagnostics import (
    AnthropicSubscriptionPolicyDiagnostic,
    ServerDiagnosticsManager,
)


@pytest.mark.asyncio
async def test_anthropic_policy_diagnostic_inactive_for_other_models() -> None:
    diagnostic = AnthropicSubscriptionPolicyDiagnostic()
    mock_configs = SimpleNamespace(
        model_cfg=SimpleNamespace(model="openai/gpt-4o", api_key="sk-test-openai")
    )
    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=mock_configs),
    ):
        report = await diagnostic.check_health()
        assert report.status == "pass"
        assert report.code == "OK_ANTHROPIC_POLICY_INACTIVE"
        assert report.component_name == "AnthropicPolicyDoctor"


@pytest.mark.asyncio
async def test_anthropic_policy_diagnostic_pass_with_dedicated_api_key() -> None:
    diagnostic = AnthropicSubscriptionPolicyDiagnostic()
    mock_configs = SimpleNamespace(
        model_cfg=SimpleNamespace(
            model="anthropic/claude-3-5-sonnet", api_key="sk-ant-api03-validkey"
        )
    )
    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=mock_configs),
    ):
        report = await diagnostic.check_health()
        assert report.status == "pass"
        assert report.code == "OK_ANTHROPIC_API_KEY_CONFIGURED"
        assert "dedicated API Key" in report.message


@pytest.mark.asyncio
async def test_anthropic_policy_diagnostic_warn_without_api_key_subscription() -> None:
    diagnostic = AnthropicSubscriptionPolicyDiagnostic()
    mock_configs = SimpleNamespace(
        model_cfg=SimpleNamespace(
            model="anthropic/claude-3-5-sonnet", api_key=""
        )
    )
    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=mock_configs),
    ):
        report = await diagnostic.check_health()
        assert report.status == "warn"
        assert report.code == "WARN_ANTHROPIC_SUBSCRIPTION_POLICY"
        assert "third-party harness policy restrictions" in report.message
        assert report.fix_suggestion is not None
        assert "Anthropic API Key" in report.fix_suggestion


@pytest.mark.asyncio
async def test_server_diagnostics_manager_includes_anthropic_probe() -> None:
    manager = ServerDiagnosticsManager()
    assert any(
        isinstance(p, AnthropicSubscriptionPolicyDiagnostic) for p in manager._probes
    )
