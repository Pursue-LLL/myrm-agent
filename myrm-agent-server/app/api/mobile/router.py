"""Mobile Device Management and Wireless ADB Pairing API.

[INPUT]
- myrm_agent_harness.toolkits.mobile_adb (POS: mobile adb session and driver)

[OUTPUT]
- GET /api/mobile/devices: List connected and known wireless Android devices
- POST /api/mobile/devices/pair: Pair Android 11+ device via pairing code
- POST /api/mobile/devices/connect: Connect to paired Android device
- POST /api/mobile/devices/disconnect: Disconnect wireless device

[POS]
Server REST API surface for mobile device management and pairing workflows.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.mobile_adb.session import MobileSession
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# Global session instance for server operations
_global_mobile_session = MobileSession()


class MobileDeviceItem(BaseModel):
    device_id: str
    ip_address: str
    port: int
    status: str
    is_default: bool = False


class PairDevicePayload(BaseModel):
    host: str = Field(description="Android device IP address")
    port: int = Field(description="Pairing port shown on Android Wireless Debugging screen")
    pairing_code: str = Field(description="6-digit pairing code")


class ConnectDevicePayload(BaseModel):
    host: str = Field(description="Android device IP address")
    port: int = Field(default=5555, description="Wireless debugging connection port")


@router.get("/devices", response_model=list[MobileDeviceItem])
async def list_devices() -> list[MobileDeviceItem]:
    """List currently connected wireless Android devices."""
    items: list[MobileDeviceItem] = []
    default_dev = _global_mobile_session.default_device
    for dev in _global_mobile_session._connected_devices:
        parts = dev.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 5555
        items.append(
            MobileDeviceItem(
                device_id=dev,
                ip_address=host,
                port=port,
                status="connected",
                is_default=(dev == default_dev),
            )
        )
    return items


@router.post("/devices/pair")
async def pair_device(payload: PairDevicePayload) -> dict[str, Any]:
    """Pair an Android 11+ device using wireless debugging pairing code."""
    res = await _global_mobile_session.pair_device(
        host=payload.host,
        port=payload.port,
        pairing_code=payload.pairing_code,
    )
    if not res.success:
        raise HTTPException(status_code=400, detail=res.message)
    return {"success": True, "message": res.message}


@router.post("/devices/connect")
async def connect_device(payload: ConnectDevicePayload) -> dict[str, Any]:
    """Connect to a paired Android device over TCP."""
    res = await _global_mobile_session.connect_device(
        host=payload.host,
        port=payload.port,
    )
    if not res.success:
        raise HTTPException(status_code=400, detail=res.message)
    return {"success": True, "message": res.message}


@router.post("/devices/disconnect")
async def disconnect_device(payload: ConnectDevicePayload) -> dict[str, Any]:
    """Disconnect wireless Android device."""
    res = await _global_mobile_session.disconnect_device(
        host=payload.host,
        port=payload.port,
    )
    return {"success": res.success, "message": res.message}
