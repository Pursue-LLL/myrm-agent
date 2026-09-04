# services/device/

## Overview

Mobile Device Bridge domain. Provides Android ADB device auto-discovery, non-blocking screen frame capture with physical status bar privacy redaction, and pointer touch relay (tap/swipe/hold/keyevent).

## File Index

| File | Role | Description | I/O/P |
|---|---|---|---|
| `bridge_service.py` | Core | `DeviceBridgeService` singleton: ADB discovery, screenshot capture, PIL redaction, touch relay | ✅ |
| `__init__.py` | Facade | Public exports of service and DTOs | ✅ |

## Dependencies

- Host/SDK `adb` executable via `shutil.which` and standard SDK fallback paths
- PIL (Pillow) for geometry status bar notification redaction
- Consumed by `app.api.webui.device_routes`

## Privacy & Security

- **Physical Status Bar Redaction**: Overlays top 4.5% of mobile screen image buffer with solid black pixels before base64 serialization, physically guaranteeing notification badges and SMS OTPs do not leak into downstream multimodal prompts or browser client.
- **Subprocess Safety**: All child processes executed under `asyncio.wait_for(timeout=3.5)` with process group tree teardown on timeout.
