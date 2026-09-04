"""WebUI service package.

[INPUT]
- Submodules: auth, session, qrcode, og_metadata, device_bridge

[OUTPUT]
- Facade exports for WebUI auxiliary services and mobile device bridge

[POS]
app.services.webui: entry facade package for WebUI domain services.
"""

from __future__ import annotations

from app.services.webui.device_bridge import (
    DeviceBridgeService,
    DeviceDoctorResult,
    DeviceInfo,
    DeviceSnapshotPayload,
    TouchRelayCommand,
    device_bridge_service,
)

__all__ = [
    "DeviceBridgeService",
    "DeviceDoctorResult",
    "DeviceInfo",
    "DeviceSnapshotPayload",
    "TouchRelayCommand",
    "device_bridge_service",
]
