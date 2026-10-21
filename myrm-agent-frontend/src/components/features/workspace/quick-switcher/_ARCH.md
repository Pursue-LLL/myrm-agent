# 工作区快速切换器与多项目漫游调色板架构清单

| 文件 | 类型 | 职责描述 | 状态 |
| :--- | :--- | :--- | :--- |
| `workspaceQuickSwitcherTypes.ts` | 契约定义 | 工作区实体、Git状态、规则绑定与漫游事件核心类型 | 稳定生效 |
| `useWorkspaceQuickSwitcherStore.ts` | 状态机 | 多项目注册表管理、LRU最近访问、Tab过滤、无损漫游与全局Cmd+O快捷键监听 | 稳定生效 |
| `WorkspacePaletteItemRow.tsx` | UI组件 | 单个工作区条目，包含项目图标、路径、Git分支、变更计数、星标与新窗口漫游 | 稳定生效 |
| `WorkspaceQuickSwitcherModal.tsx` | UI组件 | 原生语义化调色板弹窗，支持全文模糊过滤、Tab分类切换、快速添加新项目与全键盘流导航 | 稳定生效 |
| `WorkspaceBreadcrumbBar.tsx` | UI组件 | 顶栏常驻的面包屑导航与快速切换触发按钮，展示当前工作区标识与快捷键微徽章 | 稳定生效 |
| `index.ts` | 统一出口 | 聚合导出工作区调色板所有类型、状态机 Hook 与视图组件 | 稳定生效 |
