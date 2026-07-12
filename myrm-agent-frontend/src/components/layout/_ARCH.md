# components/layout/ 模块架构

## 架构概述

应用壳层组件：侧栏、导航、内容区，以及全局 PageLayout 入口（shell-first + Onboarding/Boot overlay）。

## 三模式导航

| 模式 | 路径 | 用途 |
|------|------|------|
| Chat | `/`, `/c-*` | 轻量对话 |
| Work | `/work`, `/agents`, `/agent` | 多窗格工作区 |
| Projects | `/projects`, `/kanban`, `/cron` | 项目聚合 |

## Navigation Shell Contract（Next.js 16.3）

- `next.config.ts`：`cacheComponents` + `partialPrefetching` — 按 route shell 预取（侧边栏 `/[chatId]`、Settings `/settings/[tab]`）
- 高频 segment 使用 `loading.tsx` + `RouteSegmentLoading.tsx` 提供 instant fallback
- `/[chatId]`、`/settings/[tab]` 导出 `prefetch = 'allow-runtime'` 允许 runtime snapshot 参与预取
- 会话 snapshot 读取：LRU 优先保留 agent/模式；Work pane 仅在 loading 或 messages 更多时 overlay 流式字段（见 `store/chat/messageManagement.ts`）
- 根 layout i18n 经 `LocalizedProviders`（Suspense 边界内读取 cookie locale），避免导航阻塞

## 文件清单

| 文件 | 职责 |
|------|------|
| `AppLayout.tsx` | 主布局：三模式路由映射、侧栏 + 内容区；`LocalBackendUnavailableBanner` + `ConfigReadinessDegradedBanner` |
| `useAppLayoutState.ts` | AppLayout 状态/effect 逻辑（响应式、Tab 路由、侧栏宽度） |
| `MobileSidebarDrawer.tsx` | 移动端滑出式 NavBar + ContentSidebar |
| `NavBar.tsx` | 侧栏导航，三模式 Tab（Chat / Work / Projects）+ 快捷入口 |
| `ContentSidebar.tsx` | 内容区侧栏（chat → 聊天历史，work → 智能体列表） |
| `PageLayout.tsx` | 根 layout：hydration 后直进 `AppLayout`；readiness 后台；Onboarding/Boot 全屏 overlay |
| `TabBar.tsx` | Work 模式多标签页栏 |
| `RouteSegmentLoading.tsx` | 路由 segment 统一 loading shell（chat/settings/dashboard） |
| `index.ts` | 导出 AppLayout、NavBar、ContentSidebar、PageLayout；**`app/layout.tsx` 须直接 `from './PageLayout'`**（勿经桶重导出，见 error-boundary/_ARCH.md） |

## 依赖

- `@/components/features/app-shell/` — BootScreen
- `@/components/features/onboarding/` — OnboardingWizard
- `@/components/features/projects/` — ProjectsDashboard
- `@/services/onboarding` — readiness 状态
