from unittest.mock import MagicMock, patch

from app.ai_agents.general_agent.factory import (
    _should_enable_cron_tools,
    _should_enable_subagent_tools,
)

_CAPS_FN = "app.platform_utils.deployment_capabilities.get_deployment_capabilities"
_FETCH_FN = "app.platform_utils.sandbox.entitlements.entitlement_guard.fetch_sandbox_entitlements"


def _make_caps(uses_cp: bool) -> MagicMock:
    caps = MagicMock()
    caps.uses_cp_entitlements = uses_cp
    return caps


def test_should_enable_subagent_tools_local():
    """In local mode (no CP entitlements), subagents are always enabled."""
    with patch(_CAPS_FN, return_value=_make_caps(uses_cp=False)):
        assert _should_enable_subagent_tools() is True


def test_should_enable_subagent_tools_sandbox_entitled():
    """In sandbox mode, subagents are enabled if the CP says so."""
    mock_entitlement = MagicMock()
    mock_entitlement.enable_subagent = True

    with (
        patch(_CAPS_FN, return_value=_make_caps(uses_cp=True)),
        patch(_FETCH_FN, return_value=mock_entitlement),
    ):
        assert _should_enable_subagent_tools() is True


def test_should_enable_subagent_tools_sandbox_not_entitled():
    """In sandbox mode, subagents are disabled if the CP says so."""
    mock_entitlement = MagicMock()
    mock_entitlement.enable_subagent = False

    with (
        patch(_CAPS_FN, return_value=_make_caps(uses_cp=True)),
        patch(_FETCH_FN, return_value=mock_entitlement),
    ):
        assert _should_enable_subagent_tools() is False


def test_should_enable_subagent_tools_sandbox_cp_down():
    """In sandbox mode, subagents fail closed if the CP is unreachable."""
    with (
        patch(_CAPS_FN, return_value=_make_caps(uses_cp=True)),
        patch(_FETCH_FN, return_value=None),
    ):
        assert _should_enable_subagent_tools() is False


def test_should_enable_cron_tools_local():
    """In local mode (no CP entitlements), cron tools are always enabled."""
    with patch(_CAPS_FN, return_value=_make_caps(uses_cp=False)):
        assert _should_enable_cron_tools() is True


def test_should_enable_cron_tools_sandbox_entitled():
    mock_entitlement = MagicMock()
    mock_entitlement.enable_cron = True

    with (
        patch(_CAPS_FN, return_value=_make_caps(uses_cp=True)),
        patch(_FETCH_FN, return_value=mock_entitlement),
    ):
        assert _should_enable_cron_tools() is True


def test_should_enable_cron_tools_sandbox_not_entitled():
    mock_entitlement = MagicMock()
    mock_entitlement.enable_cron = False

    with (
        patch(_CAPS_FN, return_value=_make_caps(uses_cp=True)),
        patch(_FETCH_FN, return_value=mock_entitlement),
    ):
        assert _should_enable_cron_tools() is False


def test_should_enable_cron_tools_sandbox_cp_down():
    with (
        patch(_CAPS_FN, return_value=_make_caps(uses_cp=True)),
        patch(_FETCH_FN, return_value=None),
    ):
        assert _should_enable_cron_tools() is False
