# device-inspector/

## Overview

Mobile Device Live View + Interactive Inspector mirroring `browser-inspector/` and `desktop-inspector/` for mobile device @ref overlay & touch relay.

## File Index

| File                       | Role   | Description                                                                   | I/O/P |
| -------------------------- | ------ | ----------------------------------------------------------------------------- | ----- |
| DeviceLiveView.tsx         | Core   | Resizable panel with mobile screenshot + ElementOverlay + touch relay         | ✅    |
| DeviceInspectorToggle.tsx  | Core   | Floating toggle when mobile tools active or device connected                  | ✅    |
| DeviceInspectorToolbar.tsx | Core   | Toolbar with view/inspect mode, notification redaction toggle, refresh, close | ✅    |
| DeviceInstructionInput.tsx | Core   | User instruction input with mobile @ref badge                                 | ✅    |
| index.ts                   | Export | Public component exports                                                      | ✅    |

## Dependencies

- `@/store/useDeviceInspectorStore` (POS: Device Inspector state; `selectScopedDeviceViewData` for chat-scoped SSE view)
- `@/store/chat/types` (POS: BrowserRefInfo shape for overlay refs)
- `@/components/features/browser-inspector/ElementOverlay` (POS: BBox overlay rendering)
- `ChatWindowSatellites.tsx`: mounts DeviceLiveView + DeviceInspectorToggle

## Events

- SSE: `device_view_update` via `messageStreamHandler.ts` — writes `sourceChatId` from stream chat; does **not** auto-open panel
- REST refresh: `GET /webui/device/snapshot` (tags `sourceChatId` with foreground chat)
- REST touch relay: `POST /webui/device/relay` (forwards tap/swipe/scroll/hold to device bridge)
- `DeviceLiveView.tsx` / `DeviceInspectorToggle.tsx`: Scoped view via `selectScopedDeviceViewData`; close panel on **chat switch only** (`useClosePanelOnChatSwitch`)

## Privacy & Security

1. **Notification Redaction**: Automatically overlays top status bar to prevent sensitive push notifications & OTPs from entering prompt context.
2. **Touch Relay Safeguards**: Translates relative viewport coordinates to device native resolution with bounding box validation.
