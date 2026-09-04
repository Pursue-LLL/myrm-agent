"""WebUI Device Inspector API routes.

[INPUT]
- TouchRelayBody JSON payload
- chat_id and notification_redaction query params

[OUTPUT]
- GET /webui/device/snapshot: returns real/redacted frame and doctor report
- POST /webui/device/relay: dispatches touch events to attached device
- GET /webui/device/doctor: standalone health diagnostics for mobile bridge

[POS]
app.api.webui.device_routes
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.device.bridge_service import DeviceBridgeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/device", tags=["webui-device"])


class TouchRelayBody(BaseModel):
    action: str
    x: int | None = None
    y: int | None = None
    endX: int | None = None
    endY: int | None = None
    durationMs: int | None = None
    keycode: str | None = None
    deviceId: str | None = None


@router.post("/relay")
async def relay_device_touch(body: TouchRelayBody) -> JSONResponse:
    """Relay user pointer/touch interaction (tap/swipe/hold) to mobile device."""
    service = DeviceBridgeService.get_instance()
    success = await service.relay_touch(
        action=body.action,
        x=body.x,
        y=body.y,
        end_x=body.endX,
        end_y=body.endY,
        duration_ms=body.durationMs,
        keycode=body.keycode,
        device_id=body.deviceId,
    )
    return JSONResponse(content={"ok": success, "action": body.action})


@router.get("/snapshot")
async def get_device_snapshot(
    chat_id: str | None = Query(None, description="Active chat session id"),
    redact_notifications: bool = Query(True, description="Enable physical status bar redaction"),
    device_id: str | None = Query(None, description="Optional target device serial"),
) -> JSONResponse:
    """Get mobile device snapshot for the Device Inspector panel."""
    service = DeviceBridgeService.get_instance()
    payload = await service.get_device_snapshot(
        chat_id=chat_id,
        notification_redaction=redact_notifications,
        device_id=device_id,
    )

    doctor_dict: dict[str, Any] = {
        "adb_installed": payload.doctor.adb_installed,
        "adb_path": payload.doctor.adb_path,
        "connected": payload.doctor.connected,
        "active_device_serial": payload.doctor.active_device_serial,
        "diagnostic_message": payload.doctor.diagnostic_message,
        "remediation_hint": payload.doctor.remediation_hint,
        "devices_count": len(payload.doctor.devices),
    }

    return JSONResponse(
        content={
            "screenshot_base64": payload.screenshot_base64,
            "mime_type": payload.mime_type,
            "refs": payload.refs,
            "device_id": payload.device_id,
            "device_name": payload.device_name,
            "platform": payload.platform,
            "connected": payload.connected,
            "viewport_width": payload.viewport_width,
            "viewport_height": payload.viewport_height,
            "doctor": doctor_dict,
        }
    )


@router.get("/doctor")
async def get_device_doctor() -> JSONResponse:
    """Probe ADB status and connected devices for diagnostic cards."""
    service = DeviceBridgeService.get_instance()
    doctor = await service.probe_doctor()
    return JSONResponse(
        content={
            "adb_installed": doctor.adb_installed,
            "adb_available": doctor.adb_installed,
            "adb_path": doctor.adb_path,
            "connected": doctor.connected,
            "active_device_serial": doctor.active_device_serial,
            "diagnostic_message": doctor.diagnostic_message,
            "remediation_hint": doctor.remediation_hint,
            "devices": [
                {
                    "serial": d.serial,
                    "state": d.state,
                    "model": d.model,
                    "product": d.product,
                }
                for d in doctor.devices
            ],
        }
    )
