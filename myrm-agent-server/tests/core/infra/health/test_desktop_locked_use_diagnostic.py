"""Tests for DesktopLockedUseDiagnostic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.infra.health.desktop_locked_use_diagnostic import DesktopLockedUseDiagnostic
from app.services.locked_use.curtain_bridge import CurtainBridgeState


@pytest.mark.asyncio
async def test_non_macos_reports_pass_na() -> None:
    with patch("app.core.infra.health.desktop_locked_use_diagnostic.platform.system", return_value="Linux"):
        report = await DesktopLockedUseDiagnostic().check_health()
    assert report.status == "pass"
    assert report.code == "OK_DESKTOP_LOCKED_USE_N_A"


@pytest.mark.asyncio
async def test_missing_bridge_warns() -> None:
    with (
        patch("app.core.infra.health.desktop_locked_use_diagnostic.platform.system", return_value="Darwin"),
        patch(
            "app.services.locked_use.curtain_bridge.curtain_state_path",
            return_value=None,
        ),
    ):
        report = await DesktopLockedUseDiagnostic().check_health()
    assert report.status == "warn"
    assert report.code == "WARN_CURTAIN_BRIDGE_MISSING"


@pytest.mark.asyncio
async def test_locked_use_without_shell_fails() -> None:
    path = MagicMock()
    path.name = "curtain_state.json"
    state = CurtainBridgeState(
        active=False,
        pending_auto_unlock=False,
        last_physical_input_ms=0,
        shell_alive=False,
    )
    with (
        patch("app.core.infra.health.desktop_locked_use_diagnostic.platform.system", return_value="Darwin"),
        patch("app.services.locked_use.curtain_bridge.curtain_state_path", return_value=path),
        patch("app.services.locked_use.curtain_bridge.read_curtain_state", return_value=state),
        patch("app.services.locked_use.curtain_bridge.shell_alive", return_value=False),
        patch("app.services.locked_use.curtain_bridge.locked_use_enabled", return_value=True),
    ):
        report = await DesktopLockedUseDiagnostic().check_health()
    assert report.status == "fail"
    assert report.code == "ERR_DESKTOP_SHELL_UNAVAILABLE"
