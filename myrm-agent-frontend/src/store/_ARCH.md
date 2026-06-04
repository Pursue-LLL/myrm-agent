# store/

## 架构概述

Zustand 全局状态。`chat/` 承载会话、SSE 流式 reducer（`messageStreamHandler.ts` 为热点模块）；其余 `use*Store.ts` 按产品域拆分。页面应保持薄，逻辑在本目录与 `services/`。

## 子模块

| 路径 | 职责 | 备注 |
|------|------|------|
| `chat/` | 消息列表、流式事件、发送队列、类型定义 | 流式 reducer 在 `chat/messageStream/`（见 `messageStream/_ARCH.md`） |
| `config/` | 设置草稿、LiteLLM 路由生成产物 | `litellmRouting.generated.ts` 由 harness maintainer 脚本生成 |
| `memory/` | 记忆中心 UI 状态 | |
| `skill/` | 技能选择与详情状态 | |
| `tasks/` | 后台任务/命令中心 | |
| `useAuthStore.ts` | WebUI 会话 / SaaS OAuth 门控 | 本地模式不连 CP |
| `useConfigStore.ts` | 用户设置镜像 | 与 Settings sections 同步 |
| `useArtifactPortalStore.ts` | 工件门户 | 大文件，拆分候选 |
| `use*Store.ts`（根级） | 看板、审批、伴侣、浏览器检查器等 | 一域一 store |

## 依赖

- `@/services/*` — HTTP/SSE
- `@/components/features/*` — 订阅 store
- `@/lib/utils/*` — 纯函数（**勿**使用空的 `src/utils/`）

## 约束

- 新域优先新增 `useFooStore.ts` 或 `foo/` 子目录；聊天类型见 `chat/types/`（`types.ts` 仅 barrel）。
- SaaS 专用状态须与 `resolveCpBaseUrl()` / sandbox 构建标志显式分支，避免污染本地单机路径。
