# components/layout/ 模块架构

## 架构概述

应用壳层组件：侧栏、导航、内容区，以及全局 PageLayout 入口（BootScreen / Onboarding 门控）。

## 三模式导航

NavTab 定义了三种模式：`chat | work | projects`

| 模式 | 路径 | 用途 |
|------|------|------|
| Chat | `/`, `/c-*` | 轻量对话 |
| Work | `/work`, `/agents`, `/agent` | 多窗格并行工作区 + 智能体管理 |
| Projects | `/projects`, `/kanban`, `/cron`, `/artifacts` | 项目管理 Dashboard 聚合入口 |

模式切换时保持上下文：`lastChatUrl` / `lastWorkUrl` / `lastProjectsUrl` 记录各模式最后访问的 URL，返回时自动恢复。

## 文件清单

| 文件 | 职责 |
|------|------|
| `AppLayout.tsx` | 主布局：三模式路由映射、侧栏 + 内容区；local 模式后端不可用时展示 `LocalBackendUnavailableBanner` |
| `NavBar.tsx` | 侧栏导航，三模式 Tab（Chat / Work / Projects）+ 快捷入口 |
| `ContentSidebar.tsx` | 内容区侧栏（chat → 聊天历史，work → 智能体列表） |
| `PageLayout.tsx` | 根 layout 客户端入口：standalone 路由直通、Onboarding、BootScreen、AppLayout |
| `TabBar.tsx` | Work 模式多标签页栏 |
| `index.ts` | 导出 AppLayout、NavBar、ContentSidebar、PageLayout |

## 依赖

- `@/components/features/app-shell/` — BootScreen
- `@/components/features/onboarding/` — OnboardingWizard
- `@/components/features/projects/` — ProjectsDashboard
- `@/services/onboarding` — readiness 状态
