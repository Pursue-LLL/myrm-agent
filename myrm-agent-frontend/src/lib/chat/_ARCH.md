# lib/chat/

## 架构概述

聊天域共享的前端纯逻辑：会话引导与跨视图拖拽载荷契约。

## 文件清单

| 文件                    | 地位 | 职责                                                                     | I/O/P |
| ----------------------- | ---- | ------------------------------------------------------------------------ | ----- |
| `ensureActiveChatId.ts` | 核心 | 返回既有 chat id，缺失时创建会话与 pane（供 Settings 面板程序化发消息）  | ✅    |
| `priorChatDrag.ts`      | 核心 | 侧栏会话拖拽到输入框的载荷契约（MIME 常量与编解码）                      | ✅    |

## 依赖

- `@/store/useChatStore`、`@/store/useWorkspaceStore`
- `@/store/chat/types/messages` — `MentionReference`（前序会话引用 SSOT）
- 父模块 [`../_ARCH.md`](../_ARCH.md)
