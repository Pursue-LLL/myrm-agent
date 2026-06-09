# Kanban 看板 UI 模块

多任务持久化看板前端组件集——批量提交任务、拖拽排列、自动调度执行。基于 `@dnd-kit/core` 实现跨平台（鼠标/触屏/键盘）拖拽，支持批量操作和终态确认弹窗。

## 文件清单

| 文件                         | 地位 | 职责                                                                             | I/O/P |
| ---------------------------- | ---- | -------------------------------------------------------------------------------- | ----- |
| KanbanBoardView.tsx          | 核心 | 看板主视图（列布局 + DnD 上下文 + tab 切换 + Agent 泳道状态管理）                | ✅    |
| KanbanDndComponents.tsx      | 核心 | DnD 渲染组件（KanbanDropColumn + DraggableTaskCard + Running 列 Agent 泳道分组） | ✅    |
| useKanbanDnD.ts              | 核心 | 拖拽状态管理 hook（传感器/事件/破坏性确认）                                      | ✅    |
| useKanbanAddTask.ts          | 辅助 | 任务内联创建表单状态 hook                                                        | ✅    |
| KanbanTaskCard.tsx           | 核心 | 单任务卡片渲染（状态/进度/操作菜单）                                             | ✅    |
| KanbanTaskDrawer.tsx         | 辅助 | 任务详情抽屉面板                                                                 | ✅    |
| KanbanInlineAddForm.tsx      | 辅助 | 内联新增任务表单 UI                                                              | ✅    |
| KanbanBulkActionBar.tsx      | 辅助 | 批量操作工具栏                                                                   | ✅    |
| KanbanGraphView.tsx          | 辅助 | 任务依赖 DAG 可视化（含 running 节点脉冲 / failed 节点抖动动画）                | ✅    |
| KanbanPipelineWizard.tsx     | 辅助 | 流水线模板创建向导                                                               | ✅    |
| KanbanDecomposeDialog.tsx    | 辅助 | AI 任务分解对话框                                                                | ✅    |
| KanbanSpecifyDialog.tsx      | 辅助 | 任务规范化对话框                                                                 | ✅    |
| KanbanMarkdown.tsx           | 辅助 | 安全 Markdown 渲染（GFM + CodeBlock + XSS 白名单 + 可折叠）                      | ✅    |
| KanbanDiagnosticsSection.tsx | 辅助 | 任务诊断信息展示                                                                 | ✅    |
| KanbanEventTimeline.tsx      | 辅助 | 单任务事件时间线                                                                 | ✅    |
| BoardActivityFeed.tsx        | 核心 | Board 级活动流（filter pills + auto-follow + 实时追加）                          | ✅    |
| kanban-styles.ts             | 辅助 | 共享样式常量                                                                     | ✅    |

## Stale Write Guard（乐观 UI 防冲突）

`KanbanBoardView` 内置 `pendingUserWrites` ref（`Map<taskId, { targetStatus, previousStatus, ts }>`）解决 SSE 推送 reload 与用户拖拽的竞态覆盖问题：

1. **乐观更新** — 用户拖拽后立即更新本地 `tasks` 状态，无需等待 API 响应
2. **Pending Guard** — `fetchTasks` 合并服务端数据时，对 pending 中的 task 保留用户设定的 `targetStatus`，阻止 SSE reload 覆盖
3. **成功确认** — `moveTask` API 成功后移除 pending 条目，下次 reload 正常同步
4. **失败回滚** — API 失败时恢复 `previousStatus` 并 toast 提示
5. **超时安全阀** — 5s 后自动清除 pending 条目，防止泄漏

## 模块依赖

- `@/services/kanban` — API 层（Board CRUD / Task CRUD / moveTask / edges）
- `@dnd-kit/core` — 拖拽基础设施（传感器 / 碰撞检测 / DragOverlay）
- `@/components/features/app-shell/confirm-dialog` — 通用确认弹窗
- `@/hooks/useAgentName` — 智能体名称映射
- `next-intl` — 国际化（`kanban` namespace）
