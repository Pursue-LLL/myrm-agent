# desktop-inspector/

## Overview

Desktop Live View + Interactive Inspector mirroring `browser-inspector/` for native app @dref overlay.

## File Index

| File                        | Role   | Description                                                       | I/O/P |
| --------------------------- | ------ | ----------------------------------------------------------------- | ----- |
| DesktopLiveView.tsx         | Core   | Resizable panel with screenshot + ElementOverlay                  | ✅    |
| DesktopInspectorToggle.tsx  | Core   | Floating toggle when computer_use enabled or desktop tools active | ✅    |
| DesktopInspectorToolbar.tsx | Core   | View/inspect mode toolbar                                         | ✅    |
| DesktopInstructionInput.tsx | Core   | User instruction input with @dref badge                           | ✅    |
| index.ts                    | Export | Public component exports                                          | ✅    |

## Dependencies

- `@/store/useDesktopInspectorStore` (POS: Desktop Inspector state)
- `@/store/chat/types` (POS: BrowserRefInfo shape for overlay refs)
- `@/components/features/browser-inspector/ElementOverlay` (POS: BBox overlay rendering)
- `ChatWindow.tsx`: mounts DesktopLiveView + DesktopInspectorToggle

## Events

- SSE: `desktop_view_update` via `messageStreamHandler.ts`
- REST refresh: `GET /webui/desktop/snapshot` on `desktop_*` TOOL_END
