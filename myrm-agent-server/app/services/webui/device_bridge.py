"""Mobile Device Bridge service for WebUI Inspector and Agent live-view.

[INPUT]
- system adb binary (via PATH or MYRM_ADB_PATH)
- TouchRelayCommand (from WebUI Inspector or Agent turn event)

[OUTPUT]
- DeviceDoctorResult (ADB subsystem health and device list)
- DeviceSnapshotPayload (redacted screen frame and physical viewport dimensions)
- Touch relay execution status

[POS]
app.services.webui.device_bridge: singleton service bridging WebUI Device
Inspector and mobile devices (USB/TCP ADB) with subprocess lifecycle control.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import re
import shutil
import time
from typing import Literal

from PIL import Image, ImageDraw
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

# Fallback 1x1 transparent PNG if capture fails completely
FALLBACK_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class DeviceInfo(BaseModel):
    """Detailed info for an attached physical or virtual Android device."""

    serial: str
    state: str
    model: str = "Unknown Device"
    product: str = "Android"
    connection_type: Literal["usb", "tcp"] = "usb"


class DeviceDoctorResult(BaseModel):
    """Diagnostic health check for the local/remote ADB subsystem."""

    adb_available: bool
    adb_installed: bool = False
    adb_path: str | None = None
    server_running: bool = False
    devices: list[DeviceInfo] = Field(default_factory=list)
    default_device: str | None = None
    is_cloud_environment: bool = False
    diagnostic_message: str = ""

    @model_validator(mode="before")
    @classmethod
    def sync_adb_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            if "adb_installed" not in data and "adb_available" in data:
                data["adb_installed"] = bool(data["adb_available"])
            elif "adb_available" not in data and "adb_installed" in data:
                data["adb_available"] = bool(data["adb_installed"])
        return data


class DeviceSnapshotPayload(BaseModel):
    """Snapshot data returned to WebUI Device Inspector panel."""

    screenshot_base64: str
    mime_type: str = "image/png"
    refs: dict[str, dict[str, object]] = Field(default_factory=dict)
    device_id: str
    device_name: str
    platform: Literal["android", "ios", "harmony", "generic"] = "android"
    connected: bool
    viewport_width: int
    viewport_height: int
    orientation: int = 0
    notification_redacted: bool = False
    captured_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    doctor: DeviceDoctorResult | None = None


class TouchRelayCommand(BaseModel):
    """User pointer or touch command to execute on the device."""

    action: Literal["tap", "swipe", "scroll", "hold", "keyevent"]
    x: int | None = None
    y: int | None = None
    end_x: int | None = Field(default=None, alias="endX")
    end_y: int | None = Field(default=None, alias="endY")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    keycode: str | None = None
    device_id: str | None = Field(default=None, alias="deviceId")

    model_config = {"populate_by_name": True}


class DeviceBridgeService:
    """Manages ADB device communication, screen capture, and touch relay."""

    _instance: DeviceBridgeService | None = None

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cached_snapshot: DeviceSnapshotPayload | None = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 0.3  # 300ms cache throttle

    @classmethod
    def get_instance(cls) -> DeviceBridgeService:
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_adb_path(self) -> str | None:
        """Resolve ADB binary path from environment or system PATH."""
        env_path = os.environ.get("MYRM_ADB_PATH")
        if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            return env_path
        return shutil.which("adb")

    def _is_cloud(self) -> bool:
        """Determine whether the service is running in a cloud/container sandbox."""
        return (
            os.environ.get("MYRM_SANDBOX_MODE") == "1"
            or os.path.exists("/.dockerenv")
            or bool(os.environ.get("KUBERNETES_SERVICE_HOST"))
        )

    async def _run_adb_cmd(
        self,
        args: list[str],
        timeout: float = 4.0,
        binary_output: bool = False,
    ) -> tuple[int, bytes]:
        """Execute an adb command with strict timeout and zombie-process isolation."""
        adb_bin = self._get_adb_path()
        if not adb_bin:
            return -1, b"adb binary not found in PATH"

        cmd = [adb_bin, *args]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode or 0, stdout if binary_output else stdout + stderr
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            logger.warning("ADB command timed out after %ss: %s", timeout, " ".join(cmd))
            return -2, b"ADB command timed out"
        except Exception as exc:
            logger.error("Failed to execute ADB command %s: %s", " ".join(cmd), exc)
            return -3, str(exc).encode("utf-8")

    async def doctor(self) -> DeviceDoctorResult:
        """Inspect health of the ADB subsystem and discover connected devices."""
        adb_path = self._get_adb_path()
        is_cloud = self._is_cloud()

        if not adb_path:
            return DeviceDoctorResult(
                adb_available=False,
                adb_path=None,
                server_running=False,
                devices=[],
                default_device=None,
                is_cloud_environment=is_cloud,
                diagnostic_message=(
                    "ADB binary not detected. In local mode, install Android Platform-Tools "
                    "or set MYRM_ADB_PATH. In cloud sandbox, configure ADB-over-TCP tunnel."
                ),
            )

        code, output = await self._run_adb_cmd(["devices", "-l"], timeout=3.0)
        output_text = output.decode("utf-8", errors="replace")

        if code != 0:
            return DeviceDoctorResult(
                adb_available=True,
                adb_path=adb_path,
                server_running=False,
                devices=[],
                default_device=None,
                is_cloud_environment=is_cloud,
                diagnostic_message=f"ADB daemon error (exit code {code}): {output_text.strip()}",
            )

        devices: list[DeviceInfo] = []
        lines = output_text.strip().splitlines()
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial = parts[0]
            state = parts[1]

            model = "Android Device"
            product = "Android"
            for token in parts[2:]:
                if token.startswith("model:"):
                    model = token.split(":", 1)[1].replace("_", " ")
                elif token.startswith("product:"):
                    product = token.split(":", 1)[1]

            conn_type: Literal["usb", "tcp"] = "tcp" if ":" in serial else "usb"
            devices.append(
                DeviceInfo(
                    serial=serial,
                    state=state,
                    model=model,
                    product=product,
                    connection_type=conn_type,
                )
            )

        ready_devices = [d for d in devices if d.state == "device"]
        default_serial = ready_devices[0].serial if ready_devices else None

        message = (
            f"Found {len(devices)} device(s) ({len(ready_devices)} ready)."
            if devices
            else "ADB daemon is healthy, but no devices or emulators are connected."
        )

        return DeviceDoctorResult(
            adb_available=True,
            adb_path=adb_path,
            server_running=True,
            devices=devices,
            default_device=default_serial,
            is_cloud_environment=is_cloud,
            diagnostic_message=message,
        )

    async def get_device_dimensions(self, serial: str) -> tuple[int, int]:
        """Query physical or override screen dimensions via wm size."""
        code, output = await self._run_adb_cmd(["-s", serial, "shell", "wm", "size"])
        if code != 0:
            return 1080, 2400

        text = output.decode("utf-8", errors="replace")
        override_match = re.search(r"Override size:\s*(\d+)x(\d+)", text)
        if override_match:
            return int(override_match.group(1)), int(override_match.group(2))

        physical_match = re.search(r"Physical size:\s*(\d+)x(\d+)", text)
        if physical_match:
            return int(physical_match.group(1)), int(physical_match.group(2))

        return 1080, 2400

    def _redact_status_bar(self, raw_png: bytes) -> bytes:
        """Blacken top status bar to prevent push notifications leakage."""
        try:
            with Image.open(io.BytesIO(raw_png)) as img:
                # Top 4% standard status bar threshold
                status_bar_h = max(24, int(img.height * 0.04))
                draw = ImageDraw.Draw(img)
                draw.rectangle([0, 0, img.width, status_bar_h], fill=(18, 18, 18))

                out_buf = io.BytesIO()
                img.save(out_buf, format="PNG", optimize=True)
                return out_buf.getvalue()
        except Exception as exc:
            logger.warning("Notification status bar redaction failed: %s", exc)
            return raw_png

    async def get_snapshot(
        self,
        device_id: str | None = None,
        notification_redaction: bool = True,
        bypass_cache: bool = False,
    ) -> DeviceSnapshotPayload:
        """Capture screen from the targeted ADB device with redaction and caching."""
        now = time.time()
        if (
            not bypass_cache
            and self._cached_snapshot is not None
            and (now - self._cache_timestamp) < self._cache_ttl
        ):
            return self._cached_snapshot

        doctor_res = await self.doctor()
        target_serial = device_id or doctor_res.default_device

        if not doctor_res.adb_available or not target_serial:
            device_name = (
                "Cloud Sandbox (No Tunnel)"
                if doctor_res.is_cloud_environment
                else "No Device Connected"
            )
            fallback_payload = DeviceSnapshotPayload(
                screenshot_base64=FALLBACK_PNG_B64,
                mime_type="image/png",
                refs={},
                device_id="none",
                device_name=device_name,
                platform="android",
                connected=False,
                viewport_width=1080,
                viewport_height=2400,
                orientation=0,
                notification_redacted=notification_redaction,
                doctor=doctor_res,
            )
            return fallback_payload

        # Execute screencap -p
        code, raw_png = await self._run_adb_cmd(
            ["-s", target_serial, "exec-out", "screencap", "-p"],
            timeout=4.0,
            binary_output=True,
        )

        if code != 0 or len(raw_png) < 100:
            logger.warning("screencap failed for %s, return code: %s", target_serial, code)
            return DeviceSnapshotPayload(
                screenshot_base64=FALLBACK_PNG_B64,
                mime_type="image/png",
                refs={},
                device_id=target_serial,
                device_name=f"Device ({target_serial})",
                platform="android",
                connected=False,
                viewport_width=1080,
                viewport_height=2400,
                orientation=0,
                notification_redacted=notification_redaction,
                doctor=doctor_res,
            )

        if notification_redaction:
            raw_png = self._redact_status_bar(raw_png)

        width, height = await self.get_device_dimensions(target_serial)
        b64_img = base64.b64encode(raw_png).decode("utf-8")

        matched_device = next((d for d in doctor_res.devices if d.serial == target_serial), None)
        device_name = (
            f"{matched_device.model} ({target_serial})"
            if matched_device
            else f"Device ({target_serial})"
        )

        payload = DeviceSnapshotPayload(
            screenshot_base64=b64_img,
            mime_type="image/png",
            refs={},
            device_id=target_serial,
            device_name=device_name,
            platform="android",
            connected=True,
            viewport_width=width,
            viewport_height=height,
            orientation=0,
            notification_redacted=notification_redaction,
            doctor=doctor_res,
        )

        self._cached_snapshot = payload
        self._cache_timestamp = now
        return payload

    async def relay_touch(
        self,
        command: TouchRelayCommand,
        device_id: str | None = None,
    ) -> tuple[bool, str]:
        """Dispatch touch, swipe, hold or keyevent to target device."""
        async with self._lock:
            doctor_res = await self.doctor()
            target_serial = device_id or command.device_id or doctor_res.default_device

            if not doctor_res.adb_available or not target_serial:
                return False, "No active ADB device available"

            width, height = await self.get_device_dimensions(target_serial)

            if command.action == "tap":
                x = max(0, min(width, command.x if command.x is not None else width // 2))
                y = max(0, min(height, command.y if command.y is not None else height // 2))
                code, out = await self._run_adb_cmd(
                    ["-s", target_serial, "shell", "input", "tap", str(x), str(y)]
                )
                return code == 0, out.decode("utf-8", errors="replace")

            if command.action == "swipe":
                x1 = max(0, min(width, command.x if command.x is not None else width // 2))
                y1 = max(0, min(height, command.y if command.y is not None else height // 2))
                x2 = max(0, min(width, command.end_x if command.end_x is not None else x1))
                y2 = max(0, min(height, command.end_y if command.end_y is not None else y1))
                duration = max(50, min(5000, command.duration_ms or 300))
                code, out = await self._run_adb_cmd(
                    [
                        "-s",
                        target_serial,
                        "shell",
                        "input",
                        "swipe",
                        str(x1),
                        str(y1),
                        str(x2),
                        str(y2),
                        str(duration),
                    ]
                )
                return code == 0, out.decode("utf-8", errors="replace")

            if command.action == "hold":
                x = max(0, min(width, command.x if command.x is not None else width // 2))
                y = max(0, min(height, command.y if command.y is not None else height // 2))
                duration = max(500, min(5000, command.duration_ms or 1000))
                code, out = await self._run_adb_cmd(
                    [
                        "-s",
                        target_serial,
                        "shell",
                        "input",
                        "swipe",
                        str(x),
                        str(y),
                        str(x),
                        str(y),
                        str(duration),
                    ]
                )
                return code == 0, out.decode("utf-8", errors="replace")

            if command.action == "scroll":
                # Scroll is implemented as a smooth vertical or horizontal swipe
                x1 = width // 2
                y1 = int(height * 0.7)
                x2 = width // 2
                y2 = int(height * 0.3)
                code, out = await self._run_adb_cmd(
                    [
                        "-s",
                        target_serial,
                        "shell",
                        "input",
                        "swipe",
                        str(x1),
                        str(y1),
                        str(x2),
                        str(y2),
                        "250",
                    ]
                )
                return code == 0, out.decode("utf-8", errors="replace")

            if command.action == "keyevent":
                keycode = command.keycode or "KEYCODE_BACK"
                # Whitelist keycode characters to avoid shell command injection
                if not re.match(r"^[A-Za-z0-9_]+$", keycode):
                    return False, f"Invalid keycode format: {keycode}"

                code, out = await self._run_adb_cmd(
                    ["-s", target_serial, "shell", "input", "keyevent", keycode]
                )
                return code == 0, out.decode("utf-8", errors="replace")

            return False, f"Unsupported touch relay action: {command.action}"


device_bridge_service = DeviceBridgeService.get_instance()
