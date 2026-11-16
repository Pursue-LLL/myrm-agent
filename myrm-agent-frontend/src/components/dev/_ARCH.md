# dev/

## 架构概述

localhost 开发专用桥接组件，**非终端用户功能**，只存在于非生产构建：挂载点（根布局、`AppLayout`）按 `process.env.NODE_ENV !== 'production'` 渲染。供 MCP chrome-devtools / CDP E2E 在 MessageInput 水合前驱动聊天、Goal 模式与设置页。聊天桥的实现按职责分在 [e2eBridge/](e2eBridge/_ARCH.md)，本目录只放各桥的挂载组件与根层加载器。

## 文件清单

| 文件                                 | 职责                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `E2eBridgeLoader.tsx`                | 根布局（`app/layout.tsx`）里的 localhost 加载器：在 `LocalizedProviders` 的 Suspense 之外挂载 `E2EChatBridge` 与 `E2EWikiBridge`，并行负载下 Turbopack/RSC 变慢时 CDP E2E 仍能 `attachToChat`；根布局只在非生产构建里渲染它；它自己在生产构建或非 local dev host 上直接返回 null，`process.env.NODE_ENV === 'production'` 字面量让打包器丢掉对两座桥的导入，生产产物里它只剩一个返回 null 的空组件                                                        |
| `E2EChatBridge.tsx`                  | 聊天桥的挂载组件（由 `E2eBridgeLoader` 渲染）：local dev host 上在 `useLayoutEffect` 里装 `window.__MYRM_E2E_CHAT__`（成员由 `e2eBridge/members` 组装）、`window.__MYRM_E2E_SUBAGENT__`（subagent dashboard hydration：`hydrate` / `nodeCount` / `refresh`）、SSE 记录器 `window.__MYRM_E2E_RECORD_SSE__` 与发送修订标记 `window.__MYRM_E2E_SEND_TURN_REV__`；卸载时删除 `__MYRM_E2E_CHAT__`、`__MYRM_E2E_SUBAGENT__` 与 `__MYRM_E2E_BLOCK_SEARCH_SYNC__` |
| `E2EWikiBridge.tsx`                  | Wiki 设置页与迁移向导的 Chrome E2E 桥：挂载 `window.__MYRM_E2E_WIKI__` / `window.__MYRM_E2E_MIGRATION__`，由 `E2eBridgeLoader` 在根布局挂载，使注入早于路由 chunk 加载；渲染 `sr-only` 的镜像节点（`data-e2e-bridge-mirror`）                                                                                                                                                                                                                             |
| `E2ECompanionBridge.tsx`             | 由 `AppLayout` 在非生产构建挂载 `window.__MYRM_E2E_COMPANION__`：`openHealthCheck` / `getHealthCheckState`；READ chrome_e2e 签收 companion doctor 展开路径                                                                                                                                                                                                                                                                                                |
| `localDevHost.ts`                    | 开发桥的挂载守卫：`isLocalDevHost`（非生产构建里的 127.0.0.1 / localhost；生产构建与无 window 时恒为 false——桌面发行版同样从回环地址提供页面，主机名区分不了开发与发行），所有 localhost 开发桥共用，产品组件里挂 E2E 钩子的 `MobileStatusBoard`、`SkillDiscoverTab`、`useWikiOverviewData` 也用它，与 `NODE_ENV` 字面量守卫并用；不依赖 store 或 lib，也独立于产品自己的主机判定，产品判定变宽不会让开发桥与 E2E 钩子挂到更多主机上                      |
| `__tests__/localDevHost.test.ts`     | 钉住守卫的真值表：只认非生产构建里的 127.0.0.1 / localhost，其余主机（含以它们为前缀的域名）、无 window 与生产构建都拒绝                                                                                                                                                                                                                                                                                                                                  |
| `__tests__/E2eBridgeLoader.test.tsx` | 钉住加载器的挂载条件：非生产构建的回环主机上挂聊天桥与 Wiki 桥，生产构建与其他主机什么都不挂                                                                                                                                                                                                                                                                                                                                                              |
| `e2eBridge/`                         | 聊天桥的实现：成员分组与组装、发送流水线及其页面探针、SSE 捕获、发送诊断（turn trace / store timeline）、澄清卡跳过，见 [e2eBridge/_ARCH.md](e2eBridge/_ARCH.md)                                                                                                                                                                                                                                                                                          |

## 依赖

- `@/store/chat/useSubagentStore`（`E2EChatBridge`）、`@/store/useCompanionStore`、`@/store/useFeatureGateStore`（`E2ECompanionBridge`）
- `e2eBridge/`（聊天桥实现；它依赖的 store / lib 见其 `_ARCH.md`）

## 约束

- 禁止在生产构建暴露测试通道：每个开发桥与产品组件里的 E2E 钩子（`window` 上的 store 句柄与诊断、`e2e_*` 存储键、`myrm-e2e-*` 事件、`public/e2e-runtime-bootstrap.js` 的注入）都站在非生产构建的守卫之后——守卫必须直接写 `process.env.NODE_ENV` 字面量（`!== 'production'` 包住引用，或函数开头 `=== 'production'` 提前返回）；`isLocalDevHost` 只把开发桥进一步收窄到回环主机，不能单独当守卫，因为打包器只对字面量做死代码删除、不折叠函数调用，只靠函数守卫的分支会连同字符串留在生产包里；host 检测须 fail-closed
- `bun run verify:e2e-channel`（`LINT_GATES` 之一）按语法树强制上一条（含本目录里把各桥静态导入进来的 `E2eBridgeLoader.tsx`），并限定产品代码只能导入 `localDevHost` 与两处挂载点（`app/layout.tsx` 的 `E2eBridgeLoader`、`AppLayout` 的 `E2ECompanionBridge`），规则见 [scripts/_ARCH.md](../../../scripts/_ARCH.md)
- 新增 dev 桥接放本目录，并在 [components/_ARCH.md](../_ARCH.md) 登记
