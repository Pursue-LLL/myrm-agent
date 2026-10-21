# Dashboard Workspace 架构规范

## 模块定位
负责富交互式可视化产物（HTML/SVG/原型看板）的一键固定、持久化状态管理与全景响应式监控看板抽屉，实现从单次对话产物到常驻生产力工作台的跨越。

## 文件结构与职能

| 文件 | 地位 | 职责 | I/O/P |
|---|---|---|---|
| `dashboardWorkspaceTypes.ts` | 契约层 | 定义固定组件数据结构、布局列宽与工作台状态机接口 | I: 状态变更指令<br/>O: TypeScript 强类型定义<br/>P: 领域模型纯类型 |
| `useDashboardWorkspaceStore.ts` | 状态层 | 基于 Zustand 与本地持久化维护已固定组件集合与抽屉开合 | I: Pin/Unpin/更新指令<br/>O: 响应式状态与选择器<br/>P: 状态持久化与快照 |
| `PinToDashboardButton.tsx` | 交互层 | 内嵌于富文本组件工具栏的极简固定/取消固定按钮与反馈气泡 | I: 组件标识与内容片段<br/>O: 点击微交互与钉入状态反馈<br/>P: 局部 UI 交互 |
| `DashboardWidgetCard.tsx` | 组件层 | 响应式网格单卡片、头部标题编辑、1/2/3列宽即时调节与沙箱隔离渲染 | I: 单个组件实体与变更回调<br/>O: 卡片视图与局部交互<br/>P: 视图组件 |
| `DashboardWorkspaceDrawer.tsx` | 视图层 | 响应式多列网格工作台、标题快速重命名、自动刷新与沙箱化预览 | I: 已固定组件列表与过滤词<br/>O: 全景监控看板与卡片操作流<br/>P: 布局编排与沙箱呈现 |
| `index.ts` | 门面层 | 统一对外导出类型、Store 与组件 | I: 内部子模块<br/>O: 统一外部命名导出<br/>P: 门面聚合 |
