"""Tests for computer_use deploy-mode gates."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.config.computer_use_deploy import (
    is_computer_use_deploy_supported,
    is_visual_desktop_enabled,
)

_CAPS_FN = "app.platform_utils.deployment_capabilities.get_deployment_capabilities"
_FETCH_FN = "app.platform_utils.sandbox.entitlements.entitlement_guard.fetch_sandbox_entitlements"


def _make_caps(uses_cp: bool) -> MagicMock:
    caps = MagicMock()
    caps.uses_cp_entitlements = uses_cp
    return caps


def test_is_visual_desktop_enabled() -> None:
    with patch.dict("os.environ", {"VISUAL_DESKTOP": "1"}, clear=False):
        assert is_visual_desktop_enabled() is True
    with patch.dict("os.environ", {"VISUAL_DESKTOP": ""}, clear=False):
        assert is_visual_desktop_enabled() is False


def test_computer_use_supported_in_local_mode() -> None:
    with patch("app.config.computer_use_deploy.is_local_mode", return_value=True):
        assert is_computer_use_deploy_supported() is True


def test_computer_use_unsupported_in_sandbox_without_visual_desktop() -> None:
    with (
        patch("app.config.computer_use_deploy.is_local_mode", return_value=False),
        patch("app.config.computer_use_deploy.is_sandbox", return_value=True),
        patch("app.config.computer_use_deploy.is_visual_desktop_enabled", return_value=False),
    ):
        assert is_computer_use_deploy_supported() is False


def test_computer_use_supported_in_sandbox_with_vnc_entitlement() -> None:
    mock_entitlement = MagicMock()
    mock_entitlement.enable_vnc = True

    with (
        patch("app.config.computer_use_deploy.is_local_mode", return_value=False),
        patch("app.config.computer_use_deploy.is_sandbox", return_value=True),
        patch("app.config.computer_use_deploy.is_visual_desktop_enabled", return_value=True),
        patch(_CAPS_FN, return_value=_make_caps(uses_cp=True)),
        patch(_FETCH_FN, return_value=mock_entitlement),
    ):
        assert is_computer_use_deploy_supported() is True


def test_computer_use_unsupported_in_sandbox_without_vnc_entitlement() -> None:
    from app.config.computer_use_deploy import clear_vnc_entitlement_cache

    clear_vnc_entitlement_cache()
    mock_entitlement = MagicMock()
    mock_entitlement.enable_vnc = False

    with (
        patch("app.config.computer_use_deploy.is_local_mode", return_value=False),
        patch("app.config.computer_use_deploy.is_sandbox", return_value=True),
        patch("app.config.computer_use_deploy.is_visual_desktop_enabled", return_value=True),
        patch(_CAPS_FN, return_value=_make_caps(uses_cp=True)),
        patch(_FETCH_FN, return_value=mock_entitlement),
    ):
        assert is_computer_use_deploy_supported() is False


def test_vnc_entitlement_cache_avoids_repeat_fetch() -> None:
    from app.config.computer_use_deploy import clear_vnc_entitlement_cache

    clear_vnc_entitlement_cache()
    mock_entitlement = MagicMock()
    mock_entitlement.enable_vnc = True

    with (
        patch("app.config.computer_use_deploy.is_local_mode", return_value=False),
        patch("app.config.computer_use_deploy.is_sandbox", return_value=True),
        patch("app.config.computer_use_deploy.is_visual_desktop_enabled", return_value=True),
        patch(_CAPS_FN, return_value=_make_caps(uses_cp=True)),
        patch(_FETCH_FN, return_value=mock_entitlement) as fetch_mock,
    ):
        assert is_computer_use_deploy_supported() is True
        assert is_computer_use_deploy_supported() is True
        assert fetch_mock.call_count == 1
