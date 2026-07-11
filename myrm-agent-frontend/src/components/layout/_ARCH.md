# components/layout/ 模块架构

## 架构概述

应用壳层组件：侧栏、导航、内容区，以及全局 PageLayout 入口（shell-first + Onboarding/Boot overlay）。

## 三模式导航

| 模式 | 路径 | 用途 |
|------|------|------|
| Chat | `/`, `/c-*` | 轻量对话 |
| Work | `/work`, `/agents`, `/agent` | 多窗格工作区 |
| Projects | `/projects`, `/kanban`, `/cron` | 项目聚合 |

## 文件清单

| 文件 | 职责 |
|------|------|
| `AppLayout.tsx` | 主布局：三模式路由映射、侧栏 + 内容区；`LocalBackendUnavailableBanner` + `ConfigReadinessDegradedBanner` |
| `NavBar.tsx` | 侧栏导航，三模式 Tab（Chat / Work / Projects）+ 快捷入口 |
| `ContentSidebar.tsx` | 内容区侧栏（chat → 聊天历史，work → 智能体列表） |
| `PageLayout.tsx` | 根 layout：hydration 后直进 `AppLayout`；readiness 后台；Onboarding/Boot 全屏 overlay |
| `TabBar.tsx` | Work 模式多标签页栏 |
| `index.ts` | 导出 AppLayout、NavBar、ContentSidebar、PageLayout |

## 依赖

- `@/components/features/app-shell/` — BootScreen
- `@/components/features/onboarding/` — OnboardingWizard
- `@/components/features/projects/` — ProjectsDashboard
- `@/services/onboarding` — readiness 状态
