# Browser Inspector Module

Real-time browser live view with interactive element inspection.
Enables users to visually select page elements and send natural language instructions to the agent.

## Files

| File                          | Role    | Description                                                   | I/O/P |
| ----------------------------- | ------- | ------------------------------------------------------------- | ----- |
| BrowserLiveView.tsx           | Core    | Draggable side panel with screenshot view and element overlay | Yes   |
| BrowserInspectorToggle.tsx    | Core    | Floating toggle button, visible when browser is active        | Yes   |
| ElementOverlay.tsx            | Core    | BBox-based interactive element selection overlay              | Yes   |
| InspectorToolbar.tsx          | Support | Toolbar with view/inspect mode toggle, page info, refresh     | Yes   |
| InspectorInstructionInput.tsx | Support | Natural language instruction input with element badge         | Yes   |
| index.ts                      | Export  | Barrel exports                                                | -     |

## Dependencies

- `@/store/useBrowserInspectorStore` (POS: Browser Inspector state management; `selectScopedBrowserViewData` for chat-scoped SSE view)
- `@/store/chat/types` (POS: Chat type definitions — BrowserRefInfo, BrowserViewUpdateStreamEvent)
- `@/lib/utils/classnameUtils` (POS: Tailwind class name utilities)

## Integration Points

- `ChatWindow.tsx`: Mounts BrowserLiveView + BrowserInspectorToggle
- `messageStream/handlers/fileDiffEvents.ts`: Applies `browser_view_update` SSE to inspector store with `sourceChatId` from stream chat; does **not** auto-open panel (user may keep panel closed)
- `messageStream/handlers/toolLifecycleEvents.ts`: On `browser_*` TOOL_START, sets browser active and opens panel only when stream `chatId` matches foreground chat; no TOOL_END REST re-fetch
- `BrowserLiveView.tsx` / `BrowserInspectorToggle.tsx`: Render scoped view only when `viewData.sourceChatId === active chatId`; auto-close panel when user switches to a different chat
- `GET /api/v1/webui/browser/snapshot?chat_id=`: REST manual refresh scoped to active chat
