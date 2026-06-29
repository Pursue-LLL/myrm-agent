# components/layout/ 模块架构

## 架构概述

应用壳层组件：侧栏、导航、内容区，以及全局 PageLayout 入口（BootScreen / Onboarding 门控）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `AppLayout.tsx` | 主布局：侧栏 + 内容区；local 模式后端不可用时展示 `LocalBackendUnavailableBanner` |
| `NavBar.tsx` | 顶部/侧栏导航 |
| `ContentSidebar.tsx` | 内容区侧栏 |
| `PageLayout.tsx` | 根 layout 客户端入口：standalone 路由直通、Onboarding、BootScreen、AppLayout |
| `index.ts` | 导出 AppLayout、NavBar、ContentSidebar、PageLayout |

## 依赖

- `@/components/features/app-shell/` — BootScreen
- `@/components/features/onboarding/` — OnboardingWizard
- `@/services/onboarding` — readiness 状态
