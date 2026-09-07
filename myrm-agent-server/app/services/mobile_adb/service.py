"""Mobile ADB Device Session and Management Service.

[INPUT]
- myrm_agent_harness.toolkits.mobile_adb::MobileSession, MobileActionResult

[OUTPUT]
- MobileDeviceService: Manages wireless ADB devices, pairings, and session state.
- get_mobile_device_service() -> MobileDeviceService (singleton)

[POS]
Server service managing mobile device connections and interactions.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from myrm_agent_harness.toolkits.mobile_adb import (
    MobileActionResult,
    MobileSession,
)

logger = logging.getLogger(__name__)

_GLOBAL_ACTIONS = frozenset(
    {
        "back",
        "home",
        "press_back",
        "press_home",
        "press_recents",
        "launch_app",
        "stop_app",
    }
)
_SEMANTIC_ALIASES: dict[str, str] = {
    "tap": "click",
    "type_text": "input_text",
    "type": "input_text",
    "click": "click",
    "long_press": "long_press",
    "input_text": "input_text",
    "clear_text": "clear_text",
}


class MobileDeviceService:
    """Service managing mobile device discovery, wireless pairing, and actions."""

    def __init__(self) -> None:
        self._session = MobileSession()

    @property
    def session(self) -> MobileSession:
        return self._session

    async def list_devices(self) -> list[dict[str, Any]]:
        """List connected devices formatted for API response."""
        code, out, err = await self._session.driver._run_adb("devices", "-l")
        if code != 0:
            logger.warning("adb devices failed: %s", err or out)
            return []

        devices: list[dict[str, Any]] = []
        for line in out.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("List of devices"):
                continue
            parts = stripped.split()
            if len(parts) < 2:
                continue
            device_id, state = parts[0], parts[1]
            host = device_id
            port = 5555
            if ":" in device_id:
                host_part, port_part = device_id.rsplit(":", 1)
                host = host_part
                if port_part.isdigit():
                    port = int(port_part)
            model = ""
            for token in parts[2:]:
                if token.startswith("model:"):
                    model = token.removeprefix("model:")
                    break
            devices.append(
                {
                    "device_id": device_id,
                    "host": host,
                    "port": port,
                    "model": model,
                    "state": state,
                    "is_wireless": ":" in device_id,
                    "screen_info": None,
                }
            )
        return devices

    async def pair_device(
        self,
        host: str,
        pairing_port: int,
        pairing_code: str,
    ) -> tuple[bool, str]:
        """Pair with an Android device via wireless debugging code."""
        res = await self._session.pair_device(
            host=host,
            port=pairing_port,
            pairing_code=pairing_code,
        )
        return res.success, res.message or res.error or ""

    async def connect_device(self, host: str, port: int = 5555) -> tuple[bool, str]:
        """Connect to an Android device via wireless port."""
        res = await self._session.connect_device(host=host, port=port)
        return res.success, res.message or res.error or ""

    async def snapshot(self, include_screenshot: bool = True) -> dict[str, Any]:
        """Take UI snapshot of active mobile device."""
        try:
            state, screenshot_bytes = await self._session.snapshot(
                include_screenshot=include_screenshot
            )
        except ValueError as exc:
            return {
                "success": False,
                "message": str(exc),
                "error": str(exc),
                "screenshot_base64": None,
                "ui_elements": [],
            }
        except Exception as exc:
            logger.exception("Mobile snapshot failed")
            return {
                "success": False,
                "message": f"Snapshot failed: {exc}",
                "error": str(exc),
                "screenshot_base64": None,
                "ui_elements": [],
            }

        screenshot_b64: str | None = None
        if screenshot_bytes:
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("ascii")

        return {
            "success": True,
            "message": f"Snapshot captured for {state.device_id}",
            "error": None,
            "screenshot_base64": screenshot_b64,
            "ui_elements": [
                {
                    "ref_id": el.ref_id,
                    "resource_id": el.resource_id,
                    "class_name": el.class_name,
                    "package_name": el.package_name,
                    "text": el.text,
                    "content_desc": el.content_desc,
                    "bounds": list(el.bounds),
                    "center_x": el.center[0],
                    "center_y": el.center[1],
                    "is_clickable": el.clickable,
                    "is_editable": el.editable,
                }
                for el in state.elements
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
        normalized = action.strip().lower()
        res: MobileActionResult

        try:
            if normalized in _GLOBAL_ACTIONS or normalized in {"launch_app", "stop_app"}:
                global_action = {
                    "press_back": "back",
                    "press_home": "home",
                    "press_recents": "home",
                }.get(normalized, normalized)
                param = (package_name or text or "").strip()
                res = await self._session.global_action(action=global_action, param=param)
            elif normalized == "swipe":
                if x is None or y is None or end_x is None or end_y is None:
                    return {
                        "success": False,
                        "message": "swipe requires x, y, end_x, end_y",
                        "error": "MISSING_COORDS",
                        "elapsed_ms": None,
                    }
                target = self._session.get_target()
                code, out, err = await self._session.driver._run_adb(
                    "-s",
                    target,
                    "shell",
                    "input",
                    "swipe",
                    str(x),
                    str(y),
                    str(end_x),
                    str(end_y),
                )
                res = MobileActionResult(
                    success=code == 0,
                    action="swipe",
                    message=out.strip() or "swipe completed",
                    error=None if code == 0 else (err or out),
                )
            elif normalized in {"tap", "click"} and not ref_id and x is not None and y is not None:
                target = self._session.get_target()
                code, out, err = await self._session.driver._run_adb(
                    "-s",
                    target,
                    "shell",
                    "input",
                    "tap",
                    str(x),
                    str(y),
                )
                res = MobileActionResult(
                    success=code == 0,
                    action="tap",
                    message=out.strip() or f"tapped ({x},{y})",
                    error=None if code == 0 else (err or out),
                )
            else:
                semantic = _SEMANTIC_ALIASES.get(normalized)
                if semantic is None:
                    return {
                        "success": False,
                        "message": f"Unsupported action: {action}",
                        "error": "UNSUPPORTED_ACTION",
                        "elapsed_ms": None,
                    }
                if not ref_id:
                    return {
                        "success": False,
                        "message": f"Action '{action}' requires ref_id",
                        "error": "MISSING_REF",
                        "elapsed_ms": None,
                    }
                res = await self._session.interact(
                    ref=ref_id,
                    action=semantic,
                    text=text or "",
                )
        except ValueError as exc:
            return {
                "success": False,
                "message": str(exc),
                "error": str(exc),
                "elapsed_ms": None,
            }
        except Exception as exc:
            logger.exception("Mobile interact failed")
            return {
                "success": False,
                "message": f"Interaction failed: {exc}",
                "error": str(exc),
                "elapsed_ms": None,
            }

        return {
            "success": res.success,
            "message": res.message,
            "error": res.error,
            "elapsed_ms": None,
        }


_mobile_service_instance: MobileDeviceService | None = None


def get_mobile_device_service() -> MobileDeviceService:
    """Get singleton MobileDeviceService instance."""
    global _mobile_service_instance
    if _mobile_service_instance is None:
        _mobile_service_instance = MobileDeviceService()
    return _mobile_service_instance
