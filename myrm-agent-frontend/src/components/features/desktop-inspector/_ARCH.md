# desktop-inspector/

## Overview

Desktop Live View + Interactive Inspector mirroring `browser-inspector/` for native app @dref overlay.

## File Index

| File                              | Role   | Description                                                                      | I/O/P |
| --------------------------------- | ------ | -------------------------------------------------------------------------------- | ----- |
| DesktopLiveView.tsx               | Core   | Resizable panel with screenshot + ElementOverlay                                 | ✅    |
| DesktopInspectorToggle.tsx        | Core   | Floating toggle when computer_use enabled or desktop tools active                | ✅    |
| DesktopControlApprovalBanner.tsx  | Core   | SSE-driven desktop control approval card (Allow once / session / always)         | ✅    |
| DesktopControlApprovalOverlay.tsx | Core   | Always-mounted fixed overlay so approval controls render before panel chunk load | ✅    |
| DesktopInstructionInput.tsx       | Core   | User instruction input with @dref badge                                          | ✅    |
| index.ts                          | Export | Public component exports                                                         | ✅    |

## Dependencies

- `@/store/useDesktopInspectorStore` (POS: Desktop Inspector state; `selectScopedDesktopViewData` for chat-scoped SSE view)
- `@/store/chat/types` (POS: BrowserRefInfo shape for overlay refs)
- `@/components/features/browser-inspector/ElementOverlay` (POS: BBox overlay rendering)
- `ChatWindowSatellites.tsx`: mounts DesktopControlApprovalOverlay + DesktopLiveView + DesktopInspectorToggle

## Events

- SSE: `desktop_view_update` via `messageStreamHandler.ts` — writes `sourceChatId` from stream chat; does **not** auto-open panel
- SSE: `desktop_control_approval_request` — when stream chat matches foreground: `setDesktopActive(true)` + `openPanel`; approval banner always shown via `DesktopControlApprovalOverlay`
- REST refresh: `GET /webui/desktop/snapshot` on `desktop_*` TOOL_END (tags `sourceChatId` with foreground chat)
- `DesktopLiveView.tsx` / `DesktopInspectorToggle.tsx`: Scoped view via `selectScopedDesktopViewData`; close panel on **chat switch only** (`useClosePanelOnChatSwitch`)
- REST: `GET /webui/desktop/permissions` — grant probe for the permission banner (Accessibility + Screen Recording). L2 capture readiness (`probe_capture` / `capture_ready`) is owned by Settings `DesktopPermissionsCard`, Agent `CuPermissionInline`, and Doctor — not this banner.

## E2E (Chrome MCP)

- Banner testids: `desktop-control-allow-once`, `desktop-control-allow-session`, `desktop-control-allow-always`, `desktop-control-deny`
- Regression: `test_desktop_control_approval_chrome_e2e.py` — allow_once + allow_session + allow_always→Settings revoke

## Unit tests (vitest)

| File                                                                                         | Coverage                                           |
| -------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `__tests__/DesktopControlApprovalBanner.test.tsx`                                            | deny / allow-once POST + pending hidden            |
| `__tests__/DesktopLiveView.permissionBanner.test.tsx`                                        | API fail amber banner / missing-permission details |
| `../../store/__tests__/selectScopedDesktopViewData.test.ts`                                  | chat-scoped desktop viewData selector              |
| `../../store/chat/messageStream/handlers/__tests__/fileDiffEvents.desktopViewUpdate.test.ts` | DESKTOP_VIEW_UPDATE sourceChatId write             |

## Permission Guidance

When `viewData.needsPermission` is true, `DesktopLiveView` renders `PermissionBanner` that:

1. Calls `/webui/desktop/permissions` (grant-only) to distinguish Accessibility vs Screen Recording failure
2. Shows per-capability status messages (i18n: `desktopInspector.permissionDenied*`)
3. Offers "Open System Settings" via `@/lib/desktop/permissionDeepLink::openPermissionDeepLinkWithGuideFallback`
4. API failure shows amber `permissionCheckFailed` + recheck (not red permission-denied copy)
5. "Check again" re-fetches grants without page reload

Banner scope is **missing OS grants only**. Functional capture verification lives in Settings / Inline / Doctor.
