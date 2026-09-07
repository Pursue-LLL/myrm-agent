"""Mobile ADB Device Session and Management Service.

[INPUT]
- myrm_agent_harness.toolkits.mobile_adb::MobileADBSession, create_mobile_adb_session

[OUTPUT]
- MobileDeviceService: Manages wireless ADB devices, pairings, and session state.
- get_mobile_device_service() -> MobileDeviceService (singleton)

[POS]
Server service managing mobile device connections and interactions.
"""

from __future__ import annotations

import logging
from typing import Any

from myrm_agent_harness.toolkits.mobile_adb import (
    MobileActionResult,
    MobileADBSession,
    create_mobile_adb_session,
)

logger = logging.getLogger(__name__)


class MobileDeviceService:
    """Service managing mobile device discovery, wireless pairing, and actions."""

    def __init__(self) -> None:
        self._session: MobileADBSession = create_mobile_adb_session()

    @property
    def session(self) -> MobileADBSession:
        return self._session

    async def list_devices(self) -> list[dict[str, Any]]:
        """List connected devices formatted for API response."""
        devices = await self._session.list_devices()
        return [
            {
                "device_id": d.device_id,
                "host": d.host,
                "port": d.port,
                "model": d.model,
                "state": d.state,
                "is_wireless": d.is_wireless,
                "screen_info": {
                    "width": d.screen_info.width,
                    "height": d.screen_info.height,
                    "density_dpi": d.screen_info.density_dpi,
                }
                if d.screen_info
                else None,
            }
            for d in devices
        ]

    async def pair_device(
        self,
        host: str,
        pairing_port: int,
        pairing_code: str,
    ) -> tuple[bool, str]:
        """Pair with an Android device via wireless debugging code."""
        return await self._session.pair_wireless_device(
            host=host,
            pairing_port=pairing_port,
            pairing_code=pairing_code,
        )

    async def connect_device(self, host: str, port: int = 5555) -> tuple[bool, str]:
        """Connect to an Android device via wireless port."""
        return await self._session.connect_device(host=host, port=port)

    async def snapshot(self, include_screenshot: bool = True) -> dict[str, Any]:
        """Take UI snapshot of active mobile device."""
        res: MobileActionResult = await self._session.snapshot(include_screenshot=include_screenshot)
        return {
            "success": res.success,
            "message": res.message,
            "error": res.error,
            "screenshot_base64": res.screenshot_base64,
            "ui_elements": [
                {
                    "ref_id": el.ref_id,
                    "resource_id": el.resource_id,
                    "class_name": el.class_name,
                    "package_name": el.package_name,
                    "text": el.text,
                    "content_desc": el.content_desc,
                    "bounds": list(el.bounds),
                    "center_x": el.center_x,
                    "center_y": el.center_y,
                    "is_clickable": el.is_clickable,
                    "is_editable": el.is_editable,
                }
                for el in res.ui_elements
            ],
        }

    async def interact(
        self,
        action: str,
        ref_id: str | None = None,
        x: int | None = None,
        y: int | None = None,
        text: str | None = None,
        package_name: str | None = None,
        end_x: int | None = None,
        end_y: int | None = None,
    ) -> dict[str, Any]:
        """Dispatch interaction to active mobile device."""
        res: MobileActionResult = await self._session.interact(
            action=action,
            ref_id=ref_id,
            x=x,
            y=y,
            text=text,
            package_name=package_name,
            end_x=end_x,
            end_y=end_y,
        )
        return {
            "success": res.success,
            "message": res.message,
            "error": res.error,
            "elapsed_ms": res.elapsed_ms,
        }


_mobile_service_instance: MobileDeviceService | None = None


def get_mobile_device_service() -> MobileDeviceService:
    """Get singleton MobileDeviceService instance."""
    global _mobile_service_instance
    if _mobile_service_instance is None:
        _mobile_service_instance = MobileDeviceService()
    return _mobile_service_instance
