# inspector/

## 架构概述

Desktop / Browser Inspector（agent 控制镜像）的纯函数层。无 React 依赖；仅做"加载两个 inspector store 并归还 turn 控制权"的动态编排。UI hook 见 [hooks/inspector/_ARCH.md](../../hooks/inspector/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `releaseTurnInspectorControls.ts` | 核心 | 动态加载 desktop + browser inspector store，按归属 chatId 调用各自 `releaseTurnEngagement(chatId)`（仅释放该 chat 的 turn，多 pane 并行互不误关）；动态 import 失败静默（不产生 unhandled rejection） | ✅ |
| `__tests__/releaseTurnInspectorControls.test.ts` | 测试 | 两 store 均按 chatId 释放；import 失败不抛出；幂等（chatId 不匹配/未 engaged 时无副作用） | — |

## 依赖

- `@/store/useDesktopInspectorStore` / `@/store/useBrowserInspectorStore` — 动态 import（避免与 store 层静态循环）
- 消费者：`store/chat/messageStream/handlers/completionEvents.ts`（MESSAGE_END + GOAL_STATUS budget_limited）与 `store/chat/messageStream/handlers/agentControlEvents.ts`（ERROR / AGENT_CANCELLED / CONTEXT_OVERFLOW_RESET）经 `handlerDeps.releaseInspectorControls` 共享 fire-and-forget 包装调用；`store/useChatStore.ts`（stopMessage 双路径）；`store/chat/streamConsumer.ts`（stream 中断 attach false）
