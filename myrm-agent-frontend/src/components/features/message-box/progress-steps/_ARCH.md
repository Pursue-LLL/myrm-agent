# progress-steps/

## Overview
Renders agent tool-call progress in the chat message stream. Each tool type can register a dedicated card renderer.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| ProgressSteps.tsx | Core | Routes step events to tool-specific renderers | ✅ |
| renderers/SearchToolCard.tsx | Core | Unified card for `glob_tool` / `grep_tool` search results | ✅ |
| __tests__/ProgressSteps.test.tsx | Test | Unit tests for step routing | — |

## Key Dependencies

- `@/locales` — `progressSteps.searchTool` (en/zh)
- Backend `step_builder.py` — emits `glob_tool` / `grep_tool` step payloads
