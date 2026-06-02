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

- `@/store/useBrowserInspectorStore` (POS: Browser Inspector state management)
- `@/store/chat/types` (POS: Chat type definitions — BrowserRefInfo, BrowserViewUpdateStreamEvent)
- `@/lib/utils/classnameUtils` (POS: Tailwind class name utilities)

## Integration Points

- `ChatWindow.tsx`: Mounts BrowserLiveView + BrowserInspectorToggle
- `messageStreamHandler.ts`: Triggers fetchSnapshot on browser tool TOOL_START/TOOL_END events
- `GET /api/v1/webui/browser/snapshot`: REST API for fetching screenshot + ARIA refs + BBox data
