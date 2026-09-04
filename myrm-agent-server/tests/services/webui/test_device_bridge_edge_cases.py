# -*- coding: utf-8 -*-
"""
Edge case and robustness test suite for DeviceBridgeService and WebUI device bridge routes.
L4 Documentation:
- INPUT: DeviceBridgeService instance with mocked ADB process/stream anomalies.
- OUTPUT: Assertions verifying timeout handling, invalid PNG resilience, coordinate clamping, and smooth scroll.
- POS: Unit & integration test layer for mobile device bridge inspector edge cases.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from app.services.webui.device_bridge import (
    DeviceBridgeService,
    DeviceDoctorResult,
    DeviceInfo,
    TouchRelayCommand,
)


@pytest.fixture(autouse=True)
def _isolate_admin_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config.deploy_mode import get_deploy_mode
    from app.config.settings import settings

    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.setenv("WEBUI_MODE", "false")
    monkeypatch.setenv("WEBUI_REMOTE_MODE", "false")
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))
    get_deploy_mode.cache_clear()
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()
    yield
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


@pytest.fixture
def bridge_service() -> DeviceBridgeService:
    service = DeviceBridgeService()
    service._cached_snapshot = None
    service._cache_timestamp = 0.0
    return service


@pytest.mark.asyncio
async def test_subprocess_timeout_handling(bridge_service: DeviceBridgeService) -> None:
    """Verify that _run_adb_cmd kills process and returns -2 code when timeout occurs."""
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError())
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()
        mock_exec.return_value = mock_proc

        with patch.object(bridge_service, "_get_adb_path", return_value="/mock/adb"):
            code, out = await bridge_service._run_adb_cmd(["devices"], timeout=0.1)
            assert code == -2
            assert b"timed out" in out
            mock_proc.kill.assert_called_once()


def test_corrupted_png_graceful_fallback(bridge_service: DeviceBridgeService) -> None:
    """Verify that _redact_status_bar does not crash on invalid/corrupted PNG stream."""
    corrupted_data = b"NOT_A_VALID_PNG_DATA_STREAM_MALFORMED"
    redacted = bridge_service._redact_status_bar(corrupted_data)
    assert redacted == corrupted_data


@pytest.mark.asyncio
async def test_coordinate_clamping_and_scroll_action(bridge_service: DeviceBridgeService) -> None:
    """Verify bounds clamping on extreme coordinates and smooth scroll generation."""
    with (
        patch.object(bridge_service, "doctor", new_callable=AsyncMock) as mock_doc,
        patch.object(bridge_service, "_run_adb_cmd", new_callable=AsyncMock) as mock_cmd,
        patch.object(bridge_service, "get_device_dimensions", new_callable=AsyncMock) as mock_dim,
    ):
        mock_doc.return_value = DeviceDoctorResult(
            adb_available=True,
            server_running=True,
            devices=[DeviceInfo(serial="dev1", state="device")],
            default_device="dev1",
        )
        mock_cmd.return_value = (0, b"")
        mock_dim.return_value = (1080, 2400)

        # 1. Coordinate clamping: (9999, 9999) clamped to (1080, 2400)
        out_of_bounds_tap = TouchRelayCommand(action="tap", x=9999, y=9999)
        ok, _ = await bridge_service.relay_touch(out_of_bounds_tap)
        assert ok
        mock_cmd.assert_called_with(["-s", "dev1", "shell", "input", "tap", "1080", "2400"])

        # 2. Coordinate clamping: (-50, -100) clamped to (0, 0)
        negative_tap = TouchRelayCommand(action="tap", x=-50, y=-100)
        ok, _ = await bridge_service.relay_touch(negative_tap)
        assert ok
        mock_cmd.assert_called_with(["-s", "dev1", "shell", "input", "tap", "0", "0"])

        # 3. Scroll action generation
        scroll_cmd = TouchRelayCommand(action="scroll")
        ok, _ = await bridge_service.relay_touch(scroll_cmd)
        assert ok
        mock_cmd.assert_called_with(["-s", "dev1", "shell", "input", "swipe", "540", "1680", "540", "720", "250"])
