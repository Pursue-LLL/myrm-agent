# Browser Recording Module

Browser Skill Recording Wizard UI. Provides floating toggle, recording panel with
live step visualization, and skill generation form. Connects to the server via
WebSocket for real-time capture feedback.

## Files

| File                       | Role    | Description                                                    | I/O/P |
| -------------------------- | ------- | -------------------------------------------------------------- | ----- |
| BrowserRecordingPanel.tsx  | Core    | Main panel — header, recording controls, step list, skill form | Yes   |
| BrowserRecordingToggle.tsx | Core    | Floating toggle button, visible when browser active or recording | Yes   |
| RecordingStepCard.tsx      | Support | Individual recorded step card with icon, label, screenshot     | Yes   |
| index.ts                   | Export  | Barrel exports                                                 | -     |

## Dependencies

- `@/store/useBrowserRecordingStore` (POS: Browser Recording state — WebSocket, steps, skill generation)
- `@/store/useBrowserInspectorStore` (POS: Browser Inspector state — isBrowserActive flag)
- `@/lib/utils/classnameUtils` (POS: Tailwind class name utilities)
- `next-intl` — i18n translations under `chat.browserRecording` namespace

## Integration Points

- `ChatWindow.tsx`: Mounts `BrowserRecordingPanel` + `BrowserRecordingToggle`
- Server WebSocket `/ws/recording`: Real-time step streaming and recording control
- Server REST `POST /recording/generate-skill`: Skill generation from completed session
