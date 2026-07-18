# desktop-inspector/

## Overview

Desktop Live View + Interactive Inspector mirroring `browser-inspector/` for native app @dref overlay.

## File Index

| File                        | Role   | Description                                                       | I/O/P |
| --------------------------- | ------ | ----------------------------------------------------------------- | ----- |
| DesktopLiveView.tsx         | Core   | Resizable panel with screenshot + ElementOverlay                  | ✅    |
| DesktopInspectorToggle.tsx  | Core   | Floating toggle when computer_use enabled or desktop tools active | ✅    |
| DesktopControlApprovalBanner.tsx | Core   | SSE-driven desktop control approval card (Allow once / session / always) | ✅    |
| DesktopControlApprovalOverlay.tsx | Core  | Always-mounted fixed overlay so approval controls render before panel chunk load | ✅    |
| DesktopInstructionInput.tsx | Core   | User instruction input with @dref badge                           | ✅    |
| index.ts                    | Export | Public component exports                                          | ✅    |

## Dependencies

- `@/store/useDesktopInspectorStore` (POS: Desktop Inspector state)
- `@/store/chat/types` (POS: BrowserRefInfo shape for overlay refs)
- `@/components/features/browser-inspector/ElementOverlay` (POS: BBox overlay rendering)
- `ChatWindowSatellites.tsx`: mounts DesktopControlApprovalOverlay + DesktopLiveView + DesktopInspectorToggle

## Events

- SSE: `desktop_view_update` via `messageStreamHandler.ts`
- REST refresh: `GET /webui/desktop/snapshot` on `desktop_*` TOOL_END
- REST: `GET /webui/desktop/permissions` — proactive TCC permission probe (Accessibility + Screen Recording)

## E2E (Chrome MCP)

- Banner testids: `desktop-control-allow-once`, `desktop-control-deny` (`DesktopControlApprovalBanner.tsx`)
- SSE payload opens overlay via `DesktopControlApprovalOverlay` (always mounted in `ChatWindowSatellites`)
- Bridge: `window.__MYRM_E2E_CHAT__.getDesktopApprovalSnapshot()` / `getDesktopToolProgress()` (`E2EChatBridge.tsx`)

## Permission Guidance

When `viewData.needsPermission` is true, `DesktopLiveView` renders an enhanced `PermissionBanner` that:
1. Calls `/webui/desktop/permissions` to distinguish Accessibility vs Screen Recording failure
2. Shows per-capability status messages (i18n: `desktopInspector.permissionDenied*`)
3. Offers an "Open System Settings" button using `@tauri-apps/plugin-shell` deep links (macOS `x-apple.systempreferences:` URLs), falling back to Apple support page
4. Provides a "Check again" button to re-probe without page reload
