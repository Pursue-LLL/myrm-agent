# hooks/extension/

Cross-cutting hooks for browser extension ↔ WebUI integration.

## 架构概述

WebUI mount 时向 server 写入 `web_ui_origin`，供 MV3 popup 深链 Settings Wiki。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `useExtensionWebUiOriginSeed.ts` | 核心 | App mount: persist `web_ui_origin` via `/extension/clip-agent` | ✅ |
| `__tests__/useExtensionWebUiOriginSeed.test.ts` | 测试 | Vitest for origin seed logic | — |

## 依赖

- `@/services/extension` — `getExtensionClipAgentConfig` / `updateExtensionClipAgentConfig`
