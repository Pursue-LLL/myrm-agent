"""Mobile Wireless ADB Devices API Router.

[INPUT]
- app.services.mobile_adb.service::get_mobile_device_service

[OUTPUT]
- list_devices: List discovered/connected Android devices
- pair_device: Pair with wireless Android device via pairing code
- connect_device: Connect to Android device via IP:Port
- snapshot_device: Capture screen screenshot and UI elements
- interact_device: Tap, type, swipe or launch app on mobile device

[POS]
Integrations router for mobile Android wireless debugging.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.services.mobile_adb.service import get_mobile_device_service

router = APIRouter()
logger = logging.getLogger(__name__)


class PairDeviceRequest(BaseModel):
    host: str = Field(description="Phone IP address (e.g. 192.168.1.100)")
    pairing_port: int = Field(description="Android Wireless Debugging pairing port (e.g. 37891)")
    pairing_code: str = Field(description="6-digit pairing code shown on phone screen")


class ConnectDeviceRequest(BaseModel):
    host: str = Field(description="Phone IP address (e.g. 192.168.1.100)")
    port: int = Field(default=5555, description="Connect port (e.g. 5555 or dynamic port)")


class InteractDeviceRequest(BaseModel):
    action: str = Field(description="Action to perform: tap, type_text, swipe, launch_app, press_back, press_home, press_recents")
    ref_id: str | None = Field(default=None, description="UI Element ref ID (e.g. '@m1')")
    x: int | None = Field(default=None, description="Target X coordinate")
    y: int | None = Field(default=None, description="Target Y coordinate")
    text: str | None = Field(default=None, description="Text to type")
    package_name: str | None = Field(default=None, description="App package name to launch")
    end_x: int | None = Field(default=None, description="End X coordinate for swipe")
    end_y: int | None = Field(default=None, description="End Y coordinate for swipe")


@router.get("/devices")
async def list_devices() -> dict[str, Any]:
    """List all connected or discovered Android devices."""
    service = get_mobile_device_service()
    devices = await service.list_devices()
    return success_response(data={"devices": devices, "total": len(devices)})


@router.post("/pair")
async def pair_device(req: PairDeviceRequest) -> dict[str, Any]:
    """Pair an Android device via wireless debugging pairing code."""
    service = get_mobile_device_service()
    ok, msg = await service.pair_device(
        host=req.host,
        pairing_port=req.pairing_port,
        pairing_code=req.pairing_code,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return success_response(data={"message": msg, "host": req.host, "paired": True})


@router.post("/connect")
async def connect_device(req: ConnectDeviceRequest) -> dict[str, Any]:
    """Connect to an Android device via wireless ADB port."""
    service = get_mobile_device_service()
    ok, msg = await service.connect_device(host=req.host, port=req.port)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return success_response(data={"message": msg, "host": req.host, "connected": True})


@router.get("/snapshot")
async def snapshot_device(include_screenshot: bool = True) -> dict[str, Any]:
    """Capture screen and UI structure from active mobile device."""
    service = get_mobile_device_service()
    result = await service.snapshot(include_screenshot=include_screenshot)
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message") or "Failed to capture snapshot",
        )
    return success_response(data=result)


@router.post("/interact")
async def interact_device(req: InteractDeviceRequest) -> dict[str, Any]:
    """Execute touch or key interaction on active mobile device."""
    service = get_mobile_device_service()
    result = await service.interact(
        action=req.action,
        ref_id=req.ref_id,
        x=req.x,
        y=req.y,
        text=req.text,
        package_name=req.package_name,
        end_x=req.end_x,
        end_y=req.end_y,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message") or "Interaction failed",
        )
    return success_response(data=result)
