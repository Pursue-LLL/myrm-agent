# components/layout/ 模块架构

## 架构概述

应用壳层组件：侧栏、导航、内容区，以及全局 PageLayout 入口（shell-first + Onboarding/Boot overlay）。

## 三模式导航

| 模式     | 路径                            | 用途         |
| -------- | ------------------------------- | ------------ |
| Chat     | `/`, `/c-*`                     | 轻量对话     |
| Work     | `/work`, `/agents`, `/agent`    | 多窗格工作区 |
| Projects | `/projects`, `/kanban`, `/cron` | 项目聚合     |

## Navigation Shell Contract（Next.js 16.3）

- `next.config.ts`：`cacheComponents` + `partialPrefetching` — 按 route shell 预取（侧边栏 `/[chatId]`、Settings `/settings/[tab]`）
- 高频 segment 使用 `loading.tsx` + `RouteSegmentLoading.tsx` 提供 instant fallback
- `/[chatId]`、`/settings/[tab]` 导出 `prefetch = 'allow-runtime'` 允许 runtime snapshot 参与预取
- 会话 snapshot 读取：LRU 优先保留 agent/模式；Work pane 仅在 loading 或 messages 更多时 overlay 流式字段（见 `store/chat/messageManagement.ts`）
- 根 layout i18n 经 `LocalizedProviders`（Suspense 边界内读取 cookie locale），避免导航阻塞

## 文件清单

| 文件                      | 职责                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AppLayout.tsx`           | 主布局：三模式路由映射、侧栏 + 内容区；`LocalBackendUnavailableBanner` + `CronSchedulerHealthBanner` + `ConfigUnreadableBanner` + `ConfigReadinessDegradedBanner`；<`lg` 的悬浮侧栏开关不在设置页与 `/mobile` 手机遥控面出现；遥控面自带状态栏与满屏看板，内容区不套 `px-4 pt-4` 页框（否则满屏看板上方多出 16px 内边距、页面凭空可滚动），仅在 ≥`lg` 套 `max-w-screen-lg` 限宽居中，宽屏桌面浏览器不被拉满                                                                                                                                                                                         |
| `useAppLayoutState.ts`    | AppLayout 状态/effect 逻辑（响应式、Tab 路由、侧栏宽度、`isRemoteSurface`：路径属于 `/mobile` 遥控面，判定来自 `lib/mobileRemote::isMobileRemotePath`）                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `MobileSidebarDrawer.tsx` | 移动端滑出式 NavBar + ContentSidebar                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `NavBar.tsx`              | 侧栏导航：头像、三模式 Tab（Chat / Work / Projects）、「更多」入口（`NavMoreMenu`）、后台任务 / 通知 / 设置，加 `navbar.bottom.tools` 扩展插槽与 macOS 交通灯自适应留白；常驻入口 8 个（头像 / 三个 Tab / 更多 / 后台任务 / 通知 / 设置；侧栏收起时另有展开按钮，远程网关激活时另有网关指示），新增页面只进「更多」，不再给侧栏添图标，该数量由 `__tests__/NavBar.railBudget.test.tsx` 逐个点名守住                                                                                                                                                                                                                                                               |
| `NavMoreMenu.tsx`         | 侧栏「更多」入口：一个带名称的按钮，下拉分「检视 / 扩展 / 工具」三组；目的地是真实 `<a>` 链接，当前路由落在菜单内时按钮高亮并带 `aria-current`，对应行带 `aria-current="page"`；下拉按可用高度封顶并可滚动，矮窗口不溢出；仅键盘关闭时把焦点还给入口，指针选择后不还（否则残留焦点环，并在已离开的页面旁重开提示气泡）；触屏行高 44px 且不显示快捷键；`skills` / `eval-lab` 悬停预热编辑器分块；工作台是停靠式面板，条目带勾选状态（`aria-checked`），其余四个是模态面板、打开时会盖住菜单，因此不显示状态；面板与全局快捷键由 `i18n/LocalizedProviders.tsx` 挂载的各自组件承担，这里只派发打开动作 |
| `useNavMoreSections.ts`   | 「更多」菜单的分组数据：检视（活动 / 系统诊断 / 安全中心 / 成长仪表盘 / 评测实验室，后者受 `enableEvalLab` 控制）、扩展（批量目录 / 技能管理 / MCP / 浏览器扩展状态）、工具（工作台 / 会话地图 / 演示文稿 / 工具选择 / 小莫中枢，快捷键文案取自各面板命名空间的 `shortcutHint`）；每个入口的图标唯一，两行不会读成同一个东西（`__tests__/useNavMoreSections.test.tsx` 守卫）；新增二级入口只改这里                                                                                                                                                                                                                                                                                              |
| `ContentSidebar.tsx`      | 内容区侧栏（chat → 聊天历史，work → 智能体列表）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `PageLayout.tsx`          | 根 layout：hydration 后直进 `AppLayout`；readiness 后台；仅云沙箱未完成 Onboarding 时出现全屏向导，本地安装直进首页（缺 Provider 由首页 `NoProviderBanner` 提示）；Boot 全屏 overlay；用 `<MotionConfig reducedMotion="user">` 包住应用内两种形态（含 `?mode=focused` 的无壳分支），让 framer-motion 过渡跟随系统「减少动态效果」偏好                                                                                                                                                                                                                                                               |
| `RouteSegmentLoading.tsx` | 路由 segment 统一 loading shell（chat/settings/dashboard）                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |

## 依赖

- `@/components/features/app-shell/` — BootScreen
- `@/components/features/onboarding/` — OnboardingWizard
- `@/components/features/projects/` — ProjectsDashboard
- `@/services/onboarding` — readiness 状态
