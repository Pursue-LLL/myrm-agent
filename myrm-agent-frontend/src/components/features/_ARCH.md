# features/

## 架构概述

按产品域划分的客户端 UI：对话、设置、记忆、看板、技能等。页面 (`src/app/*`) 保持薄壳，主要逻辑在本目录子模块中。

## 子模块（目录）

| 目录 | 职责 |
| ---- | ---- |
| `app-shell/` | 启动屏、认证/PWA 初始化器、全局对话框 |
| `chat-window/` | 主对话窗口与 Agent 配置 |
| `message-box/` | 消息渲染与操作栏 |
| `settings/` | 设置页各 Section |
| `sidebar/` | 会话列表与项目栏 |
| `kanban/` | 看板 | [_ARCH.md](kanban/_ARCH.md) |
| `memory/` | 记忆中心 |
| `skills/` | 技能管理 |
| `health/` | System Doctor |
| `browser-inspector/` | 浏览器检查器 | [_ARCH.md](browser-inspector/_ARCH.md) |
| `desktop-inspector/` | 桌面检查器 | [_ARCH.md](desktop-inspector/_ARCH.md) |
| `companion/` | 桌宠伴侣 | [_ARCH.md](companion/_ARCH.md) |

其余子目录见本文件夹列表（`artifacts/`、`cron/`、`workspace/` 等）。

## 依赖

- `@/components/primitives/*`
- `@/services/*`、`@/store/*`、`@/hooks/*`
