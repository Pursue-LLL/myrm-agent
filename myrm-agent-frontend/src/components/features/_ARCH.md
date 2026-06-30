# features/

## 架构概述

按产品域划分的客户端 UI：对话、设置、记忆、看板、技能等。页面 (`src/app/*`) 保持薄壳，主要逻辑在本目录子模块中。

## 子模块（目录）

| 目录 | 职责 | 文档 |
| ---- | ---- | ---- |
| `app-shell/` | 启动屏、认证/PWA 初始化器、全局对话框 | [_ARCH.md](app-shell/_ARCH.md) |
| `chat-window/` | 主对话窗口、审批、Agent 配置、目标 DAG | [_ARCH.md](chat-window/_ARCH.md) |
| `message-box/` | 消息渲染与进度 | [_ARCH.md](message-box/_ARCH.md) |
| `sidebar/` | 会话侧栏 | [_ARCH.md](sidebar/_ARCH.md) |
| `settings/` | 设置页各 Section（含 Settings→通信→渠道 Provider 配置卡） | [_ARCH.md](settings/_ARCH.md) |
| `memory/` | 记忆中心 | [_ARCH.md](memory/_ARCH.md) |
| `skills/` | 技能管理、进化审核 Dashboard | [_ARCH.md](skills/_ARCH.md) |
| `kanban/` | 看板 | [_ARCH.md](kanban/_ARCH.md) |
| `health/` | System Doctor | [_ARCH.md](health/_ARCH.md) |
| `onboarding/` | 首次启动向导（迁移 + 本地能力 + Cookbook） | [_ARCH.md](onboarding/_ARCH.md) |
| `workspace/` | 工作区与文件树 | [_ARCH.md](workspace/_ARCH.md) |
| `cron/` | 定时任务 UI | [_ARCH.md](cron/_ARCH.md) |
| `artifacts/` | 工件与部署 | [_ARCH.md](artifacts/_ARCH.md) |
| `companion/` | 桌宠伴侣 | [_ARCH.md](companion/_ARCH.md) |
| `mobile/` | Mobile Session Hub + 远程 HITL StatusBoard（`/mobile` 路由） | [_ARCH.md](mobile/_ARCH.md) |
| `browser-inspector/` | 浏览器检查器 | [_ARCH.md](browser-inspector/_ARCH.md) |
| `desktop-inspector/` | 桌面检查器 | [_ARCH.md](desktop-inspector/_ARCH.md) |
| `image-editor/` | 图片标注编辑器（Canvas API） | [_ARCH.md](image-editor/_ARCH.md) |

其余子目录（`agent-events/`、`eval-lab/`、`voice/` 等）均有目录级 `_ARCH.md`，见各文件夹。

## 依赖

- `@/components/primitives/*`
- `@/services/*`、`@/store/*`、`@/hooks/*`
