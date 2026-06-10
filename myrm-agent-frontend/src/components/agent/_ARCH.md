# components/agent/

## 架构概述

跨 feature 共用的智能体 UI 原语（头像、图标、选择器、编辑表单、内置智能体 i18n）。业务页面在 `features/`（如 `chat-window/agent-config-panel`、`settings/.../AgentsSection`），本目录只放可复用展示与编辑组件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AgentAvatar.tsx` | 核心 | 智能体头像（icon/emoji/image/首字母） | ✅ |
| `agent-icons.tsx` | 核心 | 内置智能体 SVG 图标注册表与 `AgentIcon` | ✅ |
| `builtin-agent-i18n.ts` | 核心 | 内置智能体多语言名称/描述 | ✅ |
| `AgentPicker.tsx` | 辅助 | 智能体下拉选择器 | — |
| `AgentEditForm.tsx` | 辅助 | 智能体创建/编辑表单 | — |
| `CommandBindingsEditor.tsx` | 辅助 | 斜杠命令绑定编辑 | — |

## 消费方（示例）

- `features/chat-window/` — `AgentBrickCard`、`AgentInfoBanner`、`AgentIndicator`
- `features/settings/sections/ai-core/` — `AgentsSection`
- `features/cron/` — 定时任务智能体展示
- `app/agents/page.tsx` — 智能体管理页
- `layout/AgentSidebarContent.tsx` — 侧栏智能体列表
- `lib/utils/avatar-utils.ts` — 头像 URL 解析（引用 `AGENT_ICON_REGISTRY`）

## 依赖

- `@/components/primitives/*`
- `@/lib/utils/*`
- 父模块 [`components/_ARCH.md`](../_ARCH.md)
