"""Mobile Device Bridge data models and input relay constants.

[INPUT]
- typing.Literal, dataclasses.dataclass

[OUTPUT]
- DeviceInfo: structured record for one ADB attached device
- DeviceDoctorReport: structured diagnostics of ADB availability and attached devices
- DeviceSnapshotPayload: typed snapshot data with real or redacted screen image
- KEYCODE_MAP / KEYCODE_SAFE_PATTERN / DUMMY_1PX_PNG: input relay constants

[POS]
app.services.device.models
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

KEYCODE_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,32}$")

KEYCODE_MAP: dict[str, str] = {
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

DUMMY_1PX_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


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
