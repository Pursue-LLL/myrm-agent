"""Mobile Device Bridge service for Android ADB device discovery, frame capture, and touch relay.

[INPUT]
- TouchRelayCommand parameters (action, x, y, endX, endY, durationMs, keycode)
- ADB binary from host environment or SDK platform-tools

[OUTPUT]
- DeviceBridgeService: singleton / facade for device inspection and relay
- DeviceSnapshotPayload: typed snapshot data with real or redacted screen image
- DeviceDoctorReport: structured diagnostics of ADB availability and attached devices

[POS]
app.services.device.bridge_service
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
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

_DEFAULT_ADB_TIMEOUT = 3.5
_SNAPSHOT_CACHE_TTL_SEC = 0.30
_KEYCODE_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,32}$")

_KEYCODE_MAP: dict[str, str] = {
    "back": "KEYCODE_BACK",
    "home": "KEYCODE_HOME",
    "recents": "KEYCODE_APP_SWITCH",
    "power": "KEYCODE_POWER",
    "wake": "KEYCODE_WAKEUP",
    "enter": "KEYCODE_ENTER",
    "tab": "KEYCODE_TAB",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
}

_DUMMY_1PX_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    serial: str
    state: str
    product: str
    model: str
    device: str


@dataclass(frozen=True, slots=True)
class DeviceDoctorReport:
    adb_installed: bool
    adb_path: str | None
    devices: list[DeviceInfo]
    connected: bool
    active_device_serial: str | None
    diagnostic_message: str
    remediation_hint: str | None


@dataclass(frozen=True, slots=True)
class DeviceSnapshotPayload:
    screenshot_base64: str
    mime_type: str
    refs: dict[str, object]
    device_id: str
    device_name: str
    platform: Literal["android", "ios", "harmony", "generic"]
    connected: bool
    viewport_width: int
    viewport_height: int
    doctor: DeviceDoctorReport


class DeviceBridgeService:
    """Service handling ADB device probing, frame capture, and touch input relays."""

    _instance: DeviceBridgeService | None = None

    def __init__(self, adb_path_override: str | None = None) -> None:
        self._adb_path_override = adb_path_override
        self._last_snapshot_time: float = 0.0
        self._last_snapshot_key: str = ""
        self._cached_snapshot: DeviceSnapshotPayload | None = None

    @classmethod
    def get_instance(cls) -> DeviceBridgeService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def resolve_adb_path(self) -> str | None:
        """Find ADB executable in PATH or standard Android SDK directories."""
        if self._adb_path_override and os.path.isfile(self._adb_path_override):
            return self._adb_path_override

        found = shutil.which("adb")
        if found:
            return found

        home = os.path.expanduser("~")
        candidate_paths = [
            os.path.join(home, "Library", "Android", "sdk", "platform-tools", "adb"),
            os.path.join(home, "Android", "Sdk", "platform-tools", "adb"),
            "/opt/android-sdk/platform-tools/adb",
            "/usr/local/bin/adb",
            "/opt/homebrew/bin/adb",
        ]
        for path in candidate_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return None

    async def _run_adb_cmd(
        self,
        *args: str,
        timeout: float = _DEFAULT_ADB_TIMEOUT,
    ) -> tuple[int, bytes, bytes]:
        adb = self.resolve_adb_path()
        if not adb:
            return -1, b"", b"ADB executable not found"

        cmd = [adb, *args]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode if proc.returncode is not None else 0, stdout, stderr
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return -1, b"", b"ADB command timed out"
        except Exception as e:
            return -1, b"", str(e).encode("utf-8")

    async def probe_doctor(self) -> DeviceDoctorReport:
        """Probe ADB installation and enumerate connected Android devices."""
        adb = self.resolve_adb_path()
        if not adb:
            return DeviceDoctorReport(
                adb_installed=False,
                adb_path=None,
                devices=[],
                connected=False,
                active_device_serial=None,
                diagnostic_message="ADB not found in system PATH or standard Android SDK locations.",
                remediation_hint="Install Android platform-tools via Homebrew ('brew install android-platform-tools') or Android Studio SDK Manager.",
            )

        code, stdout, stderr = await self._run_adb_cmd("devices", "-l")
        if code != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            return DeviceDoctorReport(
                adb_installed=True,
                adb_path=adb,
                devices=[],
                connected=False,
                active_device_serial=None,
                diagnostic_message=f"ADB execution failed: {err_msg}",
                remediation_hint="Ensure ADB daemon can start and has permissions.",
            )

        devices: list[DeviceInfo] = []
        lines = stdout.decode("utf-8", errors="replace").splitlines()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 2:
                serial, state = parts[0], parts[1]
                product, model, dev_name = "unknown", "unknown", "unknown"
                for p in parts[2:]:
                    if p.startswith("product:"):
                        product = p.split(":", 1)[1]
                    elif p.startswith("model:"):
                        model = p.split(":", 1)[1]
                    elif p.startswith("device:"):
                        dev_name = p.split(":", 1)[1]
                devices.append(
                    DeviceInfo(
                        serial=serial,
                        state=state,
                        product=product,
                        model=model,
                        device=dev_name,
                    )
                )

        connected_devices = [d for d in devices if d.state == "device"]
        has_connected = len(connected_devices) > 0
        active_serial = connected_devices[0].serial if has_connected else None

        if has_connected:
            diag = f"Active device connected: {active_serial} ({connected_devices[0].model})"
            hint = None
        elif devices:
            diag = f"Device detected with state '{devices[0].state}' (unauthorized or offline)."
            hint = "Please unlock the mobile device screen and tap 'Always allow USB debugging from this computer'."
        else:
            diag = "ADB is running, but no mobile device or emulator is detected."
            hint = "Connect your Android phone via USB cable with Developer Options enabled, or start an Android Emulator."

        return DeviceDoctorReport(
            adb_installed=True,
            adb_path=adb,
            devices=devices,
            connected=has_connected,
            active_device_serial=active_serial,
            diagnostic_message=diag,
            remediation_hint=hint,
        )

    def redact_status_bar(
        self,
        image_bytes: bytes,
        top_ratio: float = 0.045,
    ) -> tuple[bytes, int, int]:
        """Apply a physical solid color mask to the top notification bar to protect user privacy.

        Returns (masked_png_bytes, width, height).
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            width, height = image.size
            redact_height = max(1, int(height * top_ratio))

            draw = ImageDraw.Draw(image)
            draw.rectangle([(0, 0), (width, redact_height)], fill=(20, 20, 20))

            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue(), width, height
        except Exception as e:
            logger.warning("Notification redaction failed: %s", e)
            return image_bytes, 1080, 2400

    async def get_device_snapshot(
        self,
        *,
        chat_id: str | None = None,
        notification_redaction: bool = True,
        device_id: str | None = None,
    ) -> DeviceSnapshotPayload:
        """Collect current device snapshot with physical status bar redaction and throttle cache."""
        doctor = await self.probe_doctor()
        if not doctor.connected or not doctor.active_device_serial:
            return DeviceSnapshotPayload(
                screenshot_base64=_DUMMY_1PX_PNG,
                mime_type="image/png",
                refs={},
                device_id="none",
                device_name="No Device Connected",
                platform="android",
                connected=False,
                viewport_width=1080,
                viewport_height=2400,
                doctor=doctor,
            )

        serial = device_id if device_id and any(d.serial == device_id for d in doctor.devices) else doctor.active_device_serial
        cache_key = f"{serial}_{notification_redaction}"
        now = time.monotonic()
        if (
            self._cached_snapshot is not None
            and self._last_snapshot_key == cache_key
            and (now - self._last_snapshot_time) < _SNAPSHOT_CACHE_TTL_SEC
        ):
            return self._cached_snapshot

        code, stdout, stderr = await self._run_adb_cmd("-s", serial, "exec-out", "screencap", "-p")
        if code != 0 or not stdout:
            logger.error("Failed to capture screen via ADB: %s", stderr.decode("utf-8", errors="replace"))
            return DeviceSnapshotPayload(
                screenshot_base64=_DUMMY_1PX_PNG,
                mime_type="image/png",
                refs={},
                device_id=serial,
                device_name=doctor.devices[0].model if doctor.devices else "Android Device",
                platform="android",
                connected=True,
                viewport_width=1080,
                viewport_height=2400,
                doctor=doctor,
            )

        raw_bytes = stdout
        width, height = 1080, 2400
        if notification_redaction:
            raw_bytes, width, height = self.redact_status_bar(raw_bytes)
        else:
            try:
                img = Image.open(io.BytesIO(raw_bytes))
                width, height = img.size
            except Exception:
                pass

        b64 = base64.b64encode(raw_bytes).decode("ascii")
        matching = next((d for d in doctor.devices if d.serial == serial), None)
        dev_name = matching.model if matching else (doctor.devices[0].model if doctor.devices else "Android Device")

        payload = DeviceSnapshotPayload(
            screenshot_base64=b64,
            mime_type="image/png",
            refs={},
            device_id=serial,
            device_name=f"{dev_name} (ADB)",
            platform="android",
            connected=True,
            viewport_width=width,
            viewport_height=height,
            doctor=doctor,
        )
        self._cached_snapshot = payload
        self._last_snapshot_key = cache_key
        self._last_snapshot_time = now
        return payload

    async def relay_touch(
        self,
        *,
        action: str,
        x: int | None = None,
        y: int | None = None,
        end_x: int | None = None,
        end_y: int | None = None,
        duration_ms: int | None = None,
        keycode: str | None = None,
        device_id: str | None = None,
    ) -> bool:
        """Relay pointer and touch events (tap, swipe, hold, keyevent) to Android device."""
        doctor = await self.probe_doctor()
        if not doctor.connected or not doctor.active_device_serial:
            logger.warning("Touch relay dropped: No active connected device.")
            return False

        serial = device_id if device_id and any(d.serial == device_id for d in doctor.devices) else doctor.active_device_serial
        cmd_args: list[str] = ["-s", serial, "shell", "input"]

        if action == "tap" and x is not None and y is not None:
            cmd_args.extend(["tap", str(x), str(y)])
        elif action == "swipe" and x is not None and y is not None and end_x is not None and end_y is not None:
            ms = str(max(50, duration_ms or 300))
            cmd_args.extend(["swipe", str(x), str(y), str(end_x), str(end_y), ms])
        elif action == "hold" and x is not None and y is not None:
            ms = str(max(500, duration_ms or 800))
            cmd_args.extend(["swipe", str(x), str(y), str(x), str(y), ms])
        elif action == "keyevent" and keycode:
            norm_key = keycode.strip().lower()
            resolved_key = _KEYCODE_MAP.get(norm_key, keycode.strip())
            if not _KEYCODE_SAFE_PATTERN.match(resolved_key):
                logger.warning("Rejected invalid keycode for security defense: %s", keycode)
                return False
            cmd_args.extend(["keyevent", resolved_key])
        else:
            logger.warning("Unrecognized or incomplete touch relay action: %s", action)
            return False

        code, _, stderr = await self._run_adb_cmd(*cmd_args)
        if code != 0:
            logger.error("Touch relay failed: %s", stderr.decode("utf-8", errors="replace"))
            return False
        return True
