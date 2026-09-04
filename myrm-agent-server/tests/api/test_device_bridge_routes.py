"""Unit tests for DeviceBridgeService and WebUI device routes."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.webui.router import router as webui_router
from app.services.device.bridge_service import (
    DeviceBridgeService,
    DeviceDoctorReport,
    DeviceInfo,
)


@pytest.fixture
def dummy_png_bytes() -> bytes:
    img = Image.new("RGB", (100, 200), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_device_bridge_redact_status_bar(dummy_png_bytes: bytes) -> None:
    service = DeviceBridgeService(adb_path_override="/nonexistent/adb")
    redacted_bytes, width, height = service.redact_status_bar(dummy_png_bytes, top_ratio=0.1)

    assert width == 100
    assert height == 200
    assert len(redacted_bytes) > 0

    img = Image.open(io.BytesIO(redacted_bytes))
    pixel = img.getpixel((50, 5))  # Top bar region
    assert pixel == (20, 20, 20)  # Masked black color


@pytest.mark.asyncio
async def test_device_bridge_probe_doctor_not_installed() -> None:
    service = DeviceBridgeService(adb_path_override="/nonexistent/adb")
    with patch.object(service, "resolve_adb_path", return_value=None):
        doctor = await service.probe_doctor()
        assert doctor.adb_installed is False
        assert doctor.connected is False
        assert doctor.remediation_hint is not None


@pytest.mark.asyncio
async def test_device_bridge_probe_doctor_connected() -> None:
    service = DeviceBridgeService(adb_path_override="/usr/bin/adb")
    fake_devices_output = (
        b"List of devices attached\n"
        b"emulator-5554          device product:sdk_gphone64_arm64 model:Pixel_8_Pro device:emu64a\n"
    )

    with (
        patch.object(service, "resolve_adb_path", return_value="/usr/bin/adb"),
        patch.object(service, "_run_adb_cmd", AsyncMock(return_value=(0, fake_devices_output, b""))),
    ):
        doctor = await service.probe_doctor()
        assert doctor.adb_installed is True
        assert doctor.connected is True
        assert doctor.active_device_serial == "emulator-5554"
        assert len(doctor.devices) == 1
        assert doctor.devices[0].model == "Pixel_8_Pro"


@pytest.mark.asyncio
async def test_device_bridge_snapshot_and_relay(dummy_png_bytes: bytes) -> None:
    service = DeviceBridgeService(adb_path_override="/usr/bin/adb")
    fake_doctor = DeviceDoctorReport(
        adb_installed=True,
        adb_path="/usr/bin/adb",
        devices=[DeviceInfo("emulator-5554", "device", "sdk", "Pixel_8", "emu")],
        connected=True,
        active_device_serial="emulator-5554",
        diagnostic_message="Active device connected",
        remediation_hint=None,
    )

    with (
        patch.object(service, "probe_doctor", AsyncMock(return_value=fake_doctor)),
        patch.object(service, "_run_adb_cmd", AsyncMock(return_value=(0, dummy_png_bytes, b""))),
    ):
        payload = await service.get_device_snapshot(notification_redaction=True)
        assert payload.connected is True
        assert payload.device_id == "emulator-5554"
        assert len(payload.screenshot_base64) > 0

        relay_ok = await service.relay_touch(action="tap", x=100, y=200)
        assert relay_ok is True

        swipe_ok = await service.relay_touch(action="swipe", x=100, y=200, end_x=100, end_y=500, duration_ms=250)
        assert swipe_ok is True


@pytest.mark.asyncio
async def test_webui_device_routes_endpoints(dummy_png_bytes: bytes) -> None:
    app = FastAPI()
    app.include_router(webui_router)

    fake_doctor = DeviceDoctorReport(
        adb_installed=True,
        adb_path="/usr/bin/adb",
        devices=[DeviceInfo("emulator-5554", "device", "sdk", "Pixel_8", "emu")],
        connected=True,
        active_device_serial="emulator-5554",
        diagnostic_message="Connected",
        remediation_hint=None,
    )

    with (
        patch.object(DeviceBridgeService, "get_instance") as mock_get_inst,
    ):
        mock_service = AsyncMock()
        mock_service.probe_doctor.return_value = fake_doctor
        mock_service.relay_touch.return_value = True
        mock_service.get_device_snapshot.return_value = AsyncMock(
            screenshot_base64="fake_b64",
            mime_type="image/png",
            refs={},
            device_id="emulator-5554",
            device_name="Pixel_8 (ADB)",
            platform="android",
            connected=True,
            viewport_width=1080,
            viewport_height=2400,
            doctor=fake_doctor,
        )
        mock_get_inst.return_value = mock_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/webui/device/snapshot?chat_id=test-chat")
            assert resp.status_code == 200
            data = resp.json()
            assert data["device_id"] == "emulator-5554"
            assert data["doctor"]["adb_installed"] is True

            relay_resp = await client.post("/webui/device/relay", json={"action": "tap", "x": 50, "y": 80})
            assert relay_resp.status_code == 200
            assert relay_resp.json()["ok"] is True

            doc_resp = await client.get("/webui/device/doctor")
            assert doc_resp.status_code == 200
            assert doc_resp.json()["connected"] is True
