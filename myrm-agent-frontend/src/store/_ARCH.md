# store/

## 架构概述

Zustand 全局状态。`chat/` 承载会话、SSE 流式 reducer（`messageStreamHandler.ts` 为热点模块）；其余 `use*Store.ts` 按产品域拆分。页面应保持薄，逻辑在本目录与 `services/`。

### OS 级上下文切换架构 (Context Switching Architecture)
针对多标签页并行（Multi-tab Parallelism），本模块采用了类似操作系统的上下文切换设计：
- **`useChatStore` (CPU 寄存器)**：作为全局单例，永远只服务于当前处于 Active 状态的标签页，保证 320 个业务组件的极速读取，0 侵入。`stopMessage` 在 Multi-Pane（message cancel + abort；无 messageId 时 fallback chat cancel，覆盖 attach 流）与 mobile 远程（chat cancel + abort）两条路径均通过 `showI18nToast` 反馈 Stop 结果。
- **`useWorkspaceStore` (内存 RAM)**：负责持久化所有后台标签页的“现场快照（Snapshot）”和“控制句柄（AbortController）”。
- **智能路由 (Smart Updater)**：在 `messageRequest.ts` 中拦截流式更新，若流属于后台 Tab，则直接写入 `WorkspaceStore` 快照，绝不污染当前 UI。
- **快照直出 (Snapshot-First Rendering)**：切换标签页时，瞬间将 `WorkspaceStore` 中的快照恢复到 `useChatStore`，实现 0ms 极速切页。

## 子模块

| 路径 | 职责 | 备注 |
|------|------|------|
| `chat/` | 消息列表、流式事件、发送队列、类型定义 | 流式 reducer 在 `chat/messageStream/`；goal/plan 见 [chat/goals/_ARCH.md](chat/goals/_ARCH.md) |
| `config/` | 设置草稿、LiteLLM 路由生成产物、provider identity 迁移 | `litellmRouting.generated.ts` 由 harness 生成；legacy remap 见 [shared/config/_ARCH.md](../../../shared/config/_ARCH.md) · 模块文档 [config/_ARCH.md](config/_ARCH.md) |
| `memory/` | 记忆中心 UI 状态 | [_ARCH.md](memory/_ARCH.md) |
| `skill/` | 技能选择与进化草稿状态 | [_ARCH.md](skill/_ARCH.md) |
| `tasks/` | 通用后台任务 Map（`useTaskStore`） | [_ARCH.md](tasks/_ARCH.md) |
| `useAuthStore.ts` | WebUI 会话 / SaaS OAuth 门控 | 本地模式不连 CP |
| `useConfigStore.ts` | 用户设置镜像 | 与 Settings sections 同步 |
| `useArtifactPortalStore.ts` | 工件门户 | 大文件，拆分候选 |
| `useWorkspaceStore.ts` | 多标签页与上下文切换（RAM） | 负责保存后台 Tab 的快照（Snapshot）与生命周期句柄（AbortController） |
| `useFlowPadStore.ts` | FlowPad 模态窗口状态（截屏上下文、初始文本、开关） | 服务 Appshot 和 deep link 入口 |
| `useCommandStore.ts` | Slash 命令管理（系统行为 + 用户自定义命令 + 搜索 + 最近使用） | `builtinActions.ts` 定义 7 个内置命令；通过 ConfigSyncManager 跨端同步 |
| `builtinActions.ts` | 内置 Slash 命令定义（compact/focus/yolo/freeze/new/stop/model） | 被 `useCommandStore` 初始化时调用 |
| `use*Store.ts`（根级） | 看板、审批、伴侣、浏览器检查器等 | 一域一 store |

## 依赖

- `@/services/*` — HTTP/SSE
- `@/components/features/*` — 订阅 store
- `@/lib/utils/*` — 纯函数（位于 `src/lib/utils/`，无顶层 `src/utils/`）

## 约束

- 新域优先新增 `useFooStore.ts` 或 `foo/` 子目录；聊天类型见 `chat/types/`（`types.ts` 仅 barrel）。
- 桶导出政策见根 [_ARCH.md](../../_ARCH.md)「桶导出政策」表。
- SaaS 专用状态须与 `resolveCpBaseUrl()` / sandbox 构建标志显式分支，避免污染本地单机路径。
