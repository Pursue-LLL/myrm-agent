# messageStream/

## 架构概述

聊天 SSE 流式 reducer 子系统。将 `AgentStreamEvent` 合并进 `Message` 状态。

- **入口**：`handleMessageStream.ts`（dispatcher：mascot 副作用 + 顺序调用 `handlers/*`）
- **切片**：[`handlers/`](handlers/_ARCH.md) 按事件域拆分（companion / tools / completion 等）
- **纯函数**：`streamHelpers.ts`、`fileDiffMerge.ts`、`textSanitize.ts`
- **上下文**：`streamContext.ts`（`StreamCtx`、`done()`）

## 文件清单

| 文件 / 目录 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.ts` | 核心 | `StreamHandlerState` / `StreamHandlerActions` | ✅ |
| `streamContext.ts` | 核心 | 每事件 handler 上下文与 `done()` | ✅ |
| `handleMessageStream.ts` | 核心 | SSE 事件分发器 | ✅ |
| `handlers/index.ts` | 核心 | `STREAM_EVENT_HANDLERS` 顺序表 | ✅ |
| `handlers/handlerDeps.ts` | 辅助 | 切片共享 import | ✅ |
| `handlers/*.ts` | 核心 | 各 `AgentEventType` 域的状态合并 | — |
| `handlers/gapEvents.test.ts` | 测试 | CAPABILITY_GAP / SKILL_GAP 一键开启与绑定 | — |
| `streamHelpers.ts` | 辅助 | 来源合并、澄清表单、Goal 归一化 | ✅ |
| `fileDiffMerge.ts` | 辅助 | FILE_DIFF 路径匹配与 diff 择优合并 | ✅ |
| `textSanitize.ts` | 辅助 | 流式文本控制字符剥离 | ✅ |

## 依赖

- `../types/`（`../types.ts` barrel）— `AgentStreamEvent`、`Message` 等
- `../schema.ts` + `../knownSseEventTypes.ts` — SSE `type` 白名单与 harness 别名
- `./types.ts` — `StreamHandlerState` / `StreamHandlerActions`（本目录专用）
- `../messageUtils.ts`, `../memoryCitationUtils.ts`, `../archiveRestoreActions.ts`

## 入口

上层通过 `../messageStreamHandler.ts` 导入，保持路径稳定。
