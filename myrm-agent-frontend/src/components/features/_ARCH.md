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
| `projects/` | 项目域仪表盘（Kanban/Cron/Artifacts 入口聚合） | [_ARCH.md](projects/_ARCH.md) |
| `health/` | System Doctor | [_ARCH.md](health/_ARCH.md) |
| `onboarding/` | 首次启动向导（迁移 + 本地能力 + Cookbook） | [_ARCH.md](onboarding/_ARCH.md) |
| `workspace/` | 工作区与文件树 | [_ARCH.md](workspace/_ARCH.md) |
| `cron/` | 定时任务 UI | [_ARCH.md](cron/_ARCH.md) |
| `artifacts/` | 工件与部署 | [_ARCH.md](artifacts/_ARCH.md) |
| `companion/` | 桌宠伴侣 | [_ARCH.md](companion/_ARCH.md) |
| `e2ee/` | E2EE 安全状态 badge + Popover 面板 | [_ARCH.md](e2ee/_ARCH.md) |
| `mobile/` | Mobile Session Hub + 远程 HITL StatusBoard（`/mobile` 路由） | [_ARCH.md](mobile/_ARCH.md) |
| `browser-inspector/` | 浏览器检查器 | [_ARCH.md](browser-inspector/_ARCH.md) |
| `desktop-inspector/` | 桌面检查器 | [_ARCH.md](desktop-inspector/_ARCH.md) |
| `image-editor/` | 图片标注编辑器（Canvas API） | [_ARCH.md](image-editor/_ARCH.md) |
| `workspace-browser/` | 工作区内嵌文件浏览器与预览 | [_ARCH.md](workspace-browser/_ARCH.md) |
| `background-tasks/` | 后台任务面板 | [_ARCH.md](background-tasks/_ARCH.md) |
| `browser-recording/` | 浏览器录制回放 | [_ARCH.md](browser-recording/_ARCH.md) |
| `cli-agent/` / `cli-visualization/` | CLI Agent 与终端可视化 | [_ARCH.md](cli-agent/_ARCH.md) · [_ARCH.md](cli-visualization/_ARCH.md) |
| `checkpoint/` | 会话检查点 UI | [_ARCH.md](checkpoint/_ARCH.md) |
| `eval-lab/` | 评测实验室 | [_ARCH.md](eval-lab/_ARCH.md) |
| `growth/` | Growth 草稿与推广 | [_ARCH.md](growth/_ARCH.md) |
| `icons/` | 功能域专用图标（非 Lucide 通用集） | [_ARCH.md](icons/_ARCH.md) |
| `image-gen/` | 图片生成 UI | [_ARCH.md](image-gen/_ARCH.md) |
| `interactive-ui/` | Agent 渲染 UI（A2UI） | [_ARCH.md](interactive-ui/_ARCH.md) |
| `markdown-render-tools/` | Markdown 渲染扩展（Mermaid、代码块等） | [_ARCH.md](markdown-render-tools/_ARCH.md) |
| `message-actions/` / `message-input-actions/` | 消息操作与输入区动作 | [_ARCH.md](message-actions/_ARCH.md) · [_ARCH.md](message-input-actions/_ARCH.md) |
| `notifications/` | 通知中心 | [_ARCH.md](notifications/_ARCH.md) |
| `task-card/` | 任务卡片组件 | [_ARCH.md](task-card/_ARCH.md) |
| `theme/` | 主题切换 | [_ARCH.md](theme/_ARCH.md) |
| `voice/` | 语音输入/会话 UI | [_ARCH.md](voice/_ARCH.md) |
| `agent-events/` | Agent 事件时间线 | [_ARCH.md](agent-events/_ARCH.md) |
| `file-preview/` | 通用文件预览 | [_ARCH.md](file-preview/_ARCH.md) |
| `research/` | Research 三栏研究工作台（资料池 + Chat + 工件输出） | [_ARCH.md](research/_ARCH.md) |

上表覆盖当前全部 feature 子目录。新增目录须同步本表并添加目录级 `_ARCH.md`。

## 依赖

- `@/components/primitives/*`
- `@/services/*`、`@/store/*`、`@/hooks/*`
