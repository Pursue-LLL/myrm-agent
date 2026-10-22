# Interactive Widget Dashboard Architecture (`widget-dashboard`)

## 模块定位
负责交互式微应用与工件（Interactive Widgets）的会话级右侧固钉仪表盘（Pinned Dashboard Drawer）、网络权限策略动态管控（Network Policy Control: none / restricted / full）、以及多主题高清社交海报生成与多格式导出快照（Item 48 P0 · 汲取 ChatGPT Widget 生态与 Claude Artifact Snapshot 精髓）。

## 文件职责清单

| 文件名 | 类型 | 职责说明 | 状态 |
| :--- | :--- | :--- | :--- |
| `widgetDashboardTypes.ts` | 类型 | 领域类型定义：WidgetNetworkPolicy, PosterTheme, PinnedWidget, PosterExportOptions 等 | ✅ |
| `usePinnedDashboardStore.ts` | 状态库 | 管理固钉小组件列表、抽屉显隐、网络权限策略变更与导出目标状态机 | ✅ |
| `PinnedDashboardDrawer.tsx` | 抽屉组件 | 会话右侧滑动抽屉、小组件摘要卡片、网络策略选择器、海报导出触发器 | ✅ |
| `WidgetPosterExportModal.tsx` | 模态框 | 多主题（极简深灰、赛博紫、翡翠绿、日落橙）外框选择、SVG/PNG 快照下载与剪贴板复制 | ✅ |
| `index.ts` | 门面 | 统一导出类型、状态库与组件 | ✅ |
| `_ARCH.md` | 文档 | 模块定位与架构清单 | ✅ |
