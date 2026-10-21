# dev/

## 架构概述

localhost 开发专用桥接组件，**非终端用户功能**。供 MCP chrome-devtools / CDP E2E 在 MessageInput 水合前驱动聊天与 Goal 模式。

## 文件清单

| 文件                     | 职责                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `E2EChatBridge.tsx`      | 挂载 `window.__MYRM_E2E_CHAT__` … `getBrowserInspectorSnapshot`（含 `sourceChatId` / `scopedHasScreenshot`）、`simulateBrowserViewUpdate` / `simulateBrowserToolStart`（经真实 `fileDiffEvents` / `toolLifecycleEvents` 驱动 BLCV E2E）；`releaseActiveStreamForApiResume`、`retryStreamWithSameMessageId`（同 `requestMessageId` → `executeStreamWithRetry`；E2E 设 `__MYRM_E2E_DIRECT_SSE__` 跳过 multiplex；Chrome retry contract E2E 断言 `{busy:true}`）；Browser takeover 与 subagent dashboard hydration；`sendChatMessage`/`submitAndObserveTurn` 支持 `opts.ephemeralSubagents`（在 agentConfig 就绪后 merge，供 JIT 子智能体全流程 E2E 使用）；`ephSubagentsStatus` 暴露 store.agentConfig.ephemeralSubagents 应用诊断（`__MYRM_E2E_EPH_APPLIED__` / `__MYRM_E2E_EPH_OPTS__`）；`debugSecurityState`（暴露 ConfigSyncManager 缓存 securityConfig.yoloModeEnabled + store securityPreset/boundAgentId，供 securityPreset ⇄ YOLO E2E 断言前后端一致）；`AppLayout` 仅 local dev host |
| `E2ECompanionBridge.tsx` | 挂载 `window.__MYRM_E2E_COMPANION__`：`openHealthCheck` / `getHealthCheckState`；READ chrome_e2e 签收 companion doctor 展开路径                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

## 依赖

- `@/store/useChatStore`、`@/store/useProviderStore`、`@/store/chat/messageRequest`
- `@/lib/backend-health`、`@/lib/platform-readiness`

## 约束

- 禁止在生产构建路径暴露新全局 API；host 检测须 fail-closed
- 新增 dev 桥接放本目录，并在 [components/_ARCH.md](../_ARCH.md) 登记
