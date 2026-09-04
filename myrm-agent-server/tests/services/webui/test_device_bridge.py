"""Unit and integration tests for Mobile Device Bridge service and router endpoints."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.services.webui.device_bridge import (
    DeviceBridgeService,
    DeviceDoctorResult,
    DeviceInfo,
    TouchRelayCommand,
)


def _create_test_png(width: int = 100, height: int = 200, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    """Generate a valid test PNG image in-memory."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def bridge_service() -> DeviceBridgeService:
    service = DeviceBridgeService()
    # Reset internal cache
    service._cached_snapshot = None
    service._cache_timestamp = 0.0
    return service


@pytest.mark.asyncio
async def test_doctor_no_adb_available(bridge_service: DeviceBridgeService) -> None:
    """Doctor should report adb_available=False gracefully when adb binary is not found."""
    with patch.object(bridge_service, "_get_adb_path", return_value=None):
        doc = await bridge_service.doctor()
        assert not doc.adb_available
        assert doc.adb_path is None
        assert not doc.server_running
        assert len(doc.devices) == 0
        assert doc.default_device is None
        assert "ADB binary not detected" in doc.diagnostic_message


@pytest.mark.asyncio
async def test_doctor_with_devices(bridge_service: DeviceBridgeService) -> None:
    """Doctor correctly parses adb devices -l output into DeviceInfo models."""
    mock_output = (
        b"List of devices attached\n"
        b"emulator-5554          device product:sdk_gphone64_arm64 model:Pixel_8_Pro device:emu64a transport_id:1\n"
        b"192.168.1.100:5555     offline product:redfin model:Pixel_5 device:redfin transport_id:2\n"
    )
    with (
        patch.object(bridge_service, "_get_adb_path", return_value="/mock/adb"),
        patch.object(bridge_service, "_run_adb_cmd", new_callable=AsyncMock) as mock_run,
    ):
        mock_run.return_value = (0, mock_output)
        doc = await bridge_service.doctor()

        assert doc.adb_available
        assert doc.server_running
        assert len(doc.devices) == 2

        dev1 = doc.devices[0]
        assert dev1.serial == "emulator-5554"
        assert dev1.state == "device"
        assert dev1.model == "Pixel 8 Pro"
        assert dev1.connection_type == "usb"

        dev2 = doc.devices[1]
        assert dev2.serial == "192.168.1.100:5555"
        assert dev2.state == "offline"
        assert dev2.connection_type == "tcp"

        assert doc.default_device == "emulator-5554"
        assert "Found 2 device(s) (1 ready)" in doc.diagnostic_message


@pytest.mark.asyncio
async def test_snapshot_no_device_returns_fallback(bridge_service: DeviceBridgeService) -> None:
    """Snapshot returns structured disconnected fallback payload when no devices exist."""
    with patch.object(bridge_service, "doctor", new_callable=AsyncMock) as mock_doc:
        mock_doc.return_value = DeviceDoctorResult(
            adb_available=True,
            server_running=True,
            devices=[],
            default_device=None,
            is_cloud_environment=False,
            diagnostic_message="No devices",
        )
        snap = await bridge_service.get_snapshot(bypass_cache=True)
        assert not snap.connected
        assert snap.device_id == "none"
        assert snap.device_name == "No Device Connected"
        assert snap.screenshot_base64


@pytest.mark.asyncio
async def test_snapshot_success_with_notification_redaction(bridge_service: DeviceBridgeService) -> None:
    """Snapshot successfully captures screen, applies status bar redaction, and caches result."""
    test_png = _create_test_png(1080, 2400, (255, 255, 255))
    device_info = DeviceInfo(serial="emulator-5554", state="device", model="Pixel 8 Pro")

    with (
        patch.object(bridge_service, "doctor", new_callable=AsyncMock) as mock_doc,
        patch.object(bridge_service, "_run_adb_cmd", new_callable=AsyncMock) as mock_cmd,
        patch.object(bridge_service, "get_device_dimensions", new_callable=AsyncMock) as mock_dim,
    ):
        mock_doc.return_value = DeviceDoctorResult(
            adb_available=True,
            server_running=True,
            devices=[device_info],
            default_device="emulator-5554",
        )
        mock_cmd.return_value = (0, test_png)
        mock_dim.return_value = (1080, 2400)

        snap = await bridge_service.get_snapshot(device_id="emulator-5554", notification_redaction=True)
        assert snap.connected
        assert snap.device_id == "emulator-5554"
        assert snap.viewport_width == 1080
        assert snap.viewport_height == 2400
        assert snap.notification_redacted

        # Verify that the image in screenshot_base64 is a valid PNG and top status bar is blackened
        raw_decoded = base64.b64decode(snap.screenshot_base64)
        with Image.open(io.BytesIO(raw_decoded)) as img:
            assert img.width == 1080
            assert img.height == 2400
            # Pixel at top (0, 5) should be blackened (18, 18, 18) due to redaction
            pixel = img.getpixel((0, 5))
            assert pixel == (18, 18, 18)


@pytest.mark.asyncio
async def test_relay_touch_commands(bridge_service: DeviceBridgeService) -> None:
    """Relay commands (tap, swipe, hold, scroll, keyevent) format arguments correctly."""
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

        # 1. Tap
        tap_cmd = TouchRelayCommand(action="tap", x=500, y=1000)
        ok, _ = await bridge_service.relay_touch(tap_cmd)
        assert ok
        mock_cmd.assert_called_with(["-s", "dev1", "shell", "input", "tap", "500", "1000"])

        # 2. Swipe
        swipe_cmd = TouchRelayCommand(action="swipe", x=100, y=200, endX=300, endY=800, durationMs=500)
        ok, _ = await bridge_service.relay_touch(swipe_cmd)
        assert ok
        mock_cmd.assert_called_with(
            ["-s", "dev1", "shell", "input", "swipe", "100", "200", "300", "800", "500"]
        )

        # 3. Keyevent
        key_cmd = TouchRelayCommand(action="keyevent", keycode="KEYCODE_HOME")
        ok, _ = await bridge_service.relay_touch(key_cmd)
        assert ok
        mock_cmd.assert_called_with(["-s", "dev1", "shell", "input", "keyevent", "KEYCODE_HOME"])

        # 4. Keyevent with invalid injection attempt
        bad_key_cmd = TouchRelayCommand(action="keyevent", keycode="KEYCODE_BACK; rm -rf /")
        ok, err = await bridge_service.relay_touch(bad_key_cmd)
        assert not ok
        assert "Invalid keycode" in err


@pytest.mark.asyncio
async def test_router_endpoints() -> None:
    """Test HTTP API routes for device doctor, snapshot, and touch relay using minimal test app."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.webui.device_routes import router as device_router

    app = FastAPI()
    app.include_router(device_router, prefix="/webui")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. /webui/device/doctor
        res_doc = await client.get("/webui/device/doctor")
        assert res_doc.status_code == 200
        doc_json = res_doc.json()
        assert "adb_installed" in doc_json
        assert "adb_available" in doc_json
        assert "devices" in doc_json

        # 2. /webui/device/snapshot
        res_snap = await client.get("/webui/device/snapshot")
        assert res_snap.status_code == 200
        snap_json = res_snap.json()
        assert "screenshot_base64" in snap_json
        assert "viewport_width" in snap_json
        assert "connected" in snap_json

        # 3. /webui/device/relay
        res_relay = await client.post(
            "/webui/device/relay",
            json={"action": "tap", "x": 100, "y": 200},
        )
        assert res_relay.status_code == 200
        relay_json = res_relay.json()
        assert "ok" in relay_json
        assert relay_json["action"] == "tap"
