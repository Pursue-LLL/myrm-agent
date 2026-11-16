# dev/

## 架构概述

localhost 开发专用桥接组件，**非终端用户功能**。供 MCP chrome-devtools / CDP E2E 在 MessageInput 水合前驱动聊天、Goal 模式与设置页。聊天桥的实现按职责分在 [e2eBridge/](e2eBridge/_ARCH.md)，本目录只放各桥的挂载组件与根层加载器。

## 文件清单

| 文件                     | 职责                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `E2eBridgeLoader.tsx`    | 根布局（`app/layout.tsx`）里的 localhost 加载器：在 `LocalizedProviders` 的 Suspense 之外挂载 `E2EChatBridge` 与 `E2EWikiBridge`，并行负载下 Turbopack/RSC 变慢时 CDP E2E 仍能 `attachToChat`；非 local dev host 不渲染                                                                                                                                                                                                                                   |
| `E2EChatBridge.tsx`      | 聊天桥的挂载组件（由 `E2eBridgeLoader` 渲染）：local dev host 上在 `useLayoutEffect` 里装 `window.__MYRM_E2E_CHAT__`（成员由 `e2eBridge/members` 组装）、`window.__MYRM_E2E_SUBAGENT__`（subagent dashboard hydration：`hydrate` / `nodeCount` / `refresh`）、SSE 记录器 `window.__MYRM_E2E_RECORD_SSE__` 与发送修订标记 `window.__MYRM_E2E_SEND_TURN_REV__`；卸载时删除 `__MYRM_E2E_CHAT__`、`__MYRM_E2E_SUBAGENT__` 与 `__MYRM_E2E_BLOCK_SEARCH_SYNC__` |
| `E2EWikiBridge.tsx`      | Wiki 设置页与迁移向导的 Chrome E2E 桥：挂载 `window.__MYRM_E2E_WIKI__` / `window.__MYRM_E2E_MIGRATION__`，由 `E2eBridgeLoader` 在根布局挂载，使注入早于路由 chunk 加载；渲染 `sr-only` 的镜像节点（`data-e2e-bridge-mirror`）                                                                                                                                                                                                                             |
| `E2ECompanionBridge.tsx` | 由 `AppLayout` 挂载 `window.__MYRM_E2E_COMPANION__`：`openHealthCheck` / `getHealthCheckState`；READ chrome_e2e 签收 companion doctor 展开路径                                                                                                                                                                                                                                                                                                            |
| `e2eBridge/`             | 聊天桥的实现：成员分组与组装、发送流水线及其页面探针、SSE 捕获、发送诊断（turn trace / store timeline）、澄清卡跳过，见 [e2eBridge/_ARCH.md](e2eBridge/_ARCH.md)                                                                                                                                                                                                                                                                                          |

## 依赖

- `@/store/chat/useSubagentStore`（`E2EChatBridge`）、`@/store/useCompanionStore`、`@/store/useFeatureGateStore`（`E2ECompanionBridge`）
- `e2eBridge/`（聊天桥实现；它依赖的 store / lib 见其 `_ARCH.md`）

## 约束

- 禁止在生产构建路径暴露新全局 API；host 检测须 fail-closed
- 新增 dev 桥接放本目录，并在 [components/_ARCH.md](../_ARCH.md) 登记
