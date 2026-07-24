# dev/

## 架构概述

localhost 开发专用桥接组件，**非终端用户功能**。供 MCP chrome-devtools / CDP E2E 在 MessageInput 水合前驱动聊天与 Goal 模式。

## 文件清单

| 文件 | 职责 |
|------|------|
| `E2EChatBridge.tsx` | 挂载 `window.__MYRM_E2E_CHAT__`（sendMessage、Goal、`pinLiteModelForE2e`、`syncSearchServicesFromE2eApi`/`__MYRM_E2E_BLOCK_SEARCH_SYNC__` 私池 search 空时不回灌 `:8080`、`releaseActiveStreamForApiResume`、`skipActiveClarificationForE2e`、`dispatchBackgroundJobFinishAndRefresh`）；`AppLayout` 仅 local dev host |

## 依赖

- `@/store/useChatStore`、`@/store/useProviderStore`、`@/store/chat/messageRequest`
- `@/lib/backend-health`、`@/lib/platform-readiness`

## 约束

- 禁止在生产构建路径暴露新全局 API；host 检测须 fail-closed
- 新增 dev 桥接放本目录，并在 [components/_ARCH.md](../_ARCH.md) 登记
