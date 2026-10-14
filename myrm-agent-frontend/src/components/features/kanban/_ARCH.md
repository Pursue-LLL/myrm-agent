# Kanban 看板 UI 模块

多任务持久化看板前端组件集——批量提交任务、拖拽排列、自动调度执行。基于 `@dnd-kit/core` 实现跨平台（鼠标/触屏/键盘）拖拽，支持批量操作和终态确认弹窗。

## 文件清单

| 文件                                 | 地位 | 职责                                                                                                                                                                                                                                      | I/O/P |
| ------------------------------------ | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| KanbanBoardView.tsx                  | 核心 | 看板主视图（列布局 + DnD 上下文 + tab 切换 + Agent 泳道状态管理 + 责任矩阵决策过滤选择器；stats bar running 显示 `count/limit` 并发占用；删除 / 回收 / 重试 / 归档经 `useKanbanTaskActionConfirm` 统一确认，卡片、抽屉、拖拽的状态流转统一走它的 `requestMove`；移动失败只提示本地化文案，不透出服务端原文）                                                                                                 | ✅    |
| KanbanDndComponents.tsx              | 核心 | DnD 渲染（KanbanDropColumn + DraggableTaskCard + Running 泳道 + Drawer 入口；卡片自身登记为 dnd-kit activator，卡片内按钮与菜单的 Enter/Space 不会被劫持成键盘拖拽）                                                                                                                                                             | ✅    |
| useKanbanDnD.ts                      | 核心 | 拖拽状态管理 hook（传感器/事件/终态确认；服务端必拒的流转在落点拦下并提示，批量拖拽只搬能直接流转的卡片，被拦下的合并成一次提示）                                                                                                                                                                                               | ✅    |
| useKanbanAddTask.ts                  | 辅助 | 任务内联创建表单状态 hook（含 agent/model override 状态）                                                                                                                                                                                 | ✅    |
| KanbanTaskCard.tsx                   | 核心 | 单任务卡片渲染（首屏决策帧要素/推荐动作微条/状态/进度；操作入口为 KanbanTaskCardActions；附件 badge 点击打开 Drawer）                                                                                                                                              | ✅    |
| KanbanTaskCardActions.tsx            | 辅助 | 卡片单一操作菜单（详情 / Specify / Decompose / 状态流转 / 回收 / 删除，回收与删除只发起确认请求；失败任务的「就绪」入口显示为「重试」）；触发器常驻 DOM，桌面悬停或键盘聚焦显现、触屏常显（`REVEAL_ON_HOVER`）；触发器与 portal 菜单上的指针手势不冒泡给 dnd 卡片（否则按下起拖拽、双击开抽屉） | ✅    |
| KanbanTaskActionConfirm.tsx          | 辅助 | 删除 / 回收 / 重试 / 归档的确认对话框与 `useKanbanTaskActionConfirm` 状态 hook：由看板视图统一持有，卡片菜单、抽屉、拖拽只发起请求；`requestMove` 按 `resolveMoveIntent` 分流（重试与归档先确认，其余直接流转）；文案交代后果（删除连同运行记录一并清除、等待它的任务可能变为就绪并自动开跑；回收会停止执行中的 Agent 并回到就绪；重试会再次消耗模型额度；归档后任务离开看板且无法在界面恢复）；关闭动画期间保留任务标题，文案不闪空 | ✅    |
| useKanbanTaskActions.ts              | 辅助 | 回收 / 删除 / 重试 / 归档的执行函数：确认后调 API、刷新列表、给出本地化提示（失败不透出服务端原文）；归档复用看板的乐观移动 | ✅    |
| kanban-transitions.ts                | 核心 | 状态流转的单一判定点：`resolveMoveIntent(from, to)` 镜像服务端 move 守卫，返回 move / retry / archive / blocked；`moveLabelKey` 给出入口文案 key（失败 → 就绪显示「重试」）。卡片菜单、抽屉、拖拽共用 | ✅    |
| KanbanTaskDrawer.tsx                 | 辅助 | 任务详情抽屉面板入口（编排 hook 与子组件）                                                                                                                                                                                                | ✅    |
| useKanbanTaskDrawer.ts               | 辅助 | 抽屉面板状态管理 hook（数据加载/操作处理/计算属性）                                                                                                                                                                                       | ✅    |
| resolveTaskDepInfos.ts               | 辅助 | 任务依赖图节点标题解析（本地列表 + 远程 fallback）                                                                                                                                                                                        | ✅    |
| useKanbanTaskDrawerAttachments.ts    | 辅助 | 抽屉附件上传/拖拽/粘贴子 hook                                                                                                                                                                                                             | ✅    |
| useKanbanTaskDrawerWorkflow.ts       | 辅助 | Promote / Move / Reclaim 工作流子 hook（重试与归档交给看板的确认流程，抽屉随即关闭）                                                                                                                                                                                                    | ✅    |
| KanbanTaskDrawerHeader.tsx           | 辅助 | 抽屉面板头部（状态操作按钮 + Reclaim/Promote 确认）                                                                                                                                                                                       | ✅    |
| KanbanTaskDrawerDetails.tsx          | 辅助 | 抽屉详情（超时/技能/模型覆盖/审批开关/来源 Chat 与 Board 深链/ReviewCommentThread 接入）                                                                                                                                                  | ✅    |
| RaceSection.tsx                      | 辅助 | 赛马扇出与裁决（lane 数选择+变体指令+成本预估确认发起；lane 状态/token/结果展开；变更文件列表+Monaco 双栏 diff；IN_REVIEW lane 一键选 winner；事件+条件轮询实时刷新；错误码友好映射；六套 locale；Tailwind v4 主题 tokens，禁原生 emoji） | ✅    |
| ReviewCommentThread.tsx              | 辅助 | 验收标准通过/失败详情卡片与 Critical/Warning/Info 三级评审意见流展示（支持 severity 过滤、修复建议折叠展开、快捷复制与一键修复动作）                                                                                                      | ✅    |
| KanbanSkillPicker.tsx                | 辅助 | 任务技能多选选择器（搜索 + 已选 chip + 未知 id 标记；数据源 useSkillStore，创建/详情共用）                                                                                                                                                | ✅    |
| KanbanTaskDrawerBodySections.tsx     | 辅助 | 抽屉附件与结果区段组件                                                                                                                                                                                                                    | ✅    |
| KanbanTaskDrawerBodyMetaSections.tsx | 辅助 | 抽屉依赖/评论/进度区段组件                                                                                                                                                                                                                | ✅    |
| KanbanInlineAddForm.tsx              | 辅助 | 内联新增任务表单 UI（标题/描述/agent/模型覆盖/技能/超时/依赖）                                                                                                                                                                            | ✅    |
| KanbanBulkActionBar.tsx              | 辅助 | 批量操作工具栏（归档与删除都在原位二次确认，同一时刻只开一个）                                                                                                                                                                                                                            | ✅    |
| KanbanGraphView.tsx                  | 辅助 | 任务依赖 DAG 可视化（含 running 节点脉冲 / failed 节点抖动动画；依赖连线按父任务状态着色——已完成为 emerald 实线，阻塞 / 失败为红色虚线，小地图同色，颜色取主题变量或带回退的 Tailwind 色阶，不包 `hsl()`）                                                                                                                                                                          | ✅    |
| KanbanPipelineWizard.tsx             | 辅助 | 流水线模板创建向导（支持 repeat_for fan-out 模板的 multi-select 动态并行任务创建）                                                                                                                                                        | ✅    |
| KanbanDecomposeDialog.tsx            | 辅助 | AI 任务分解对话框                                                                                                                                                                                                                         | ✅    |
| KanbanSpecifyDialog.tsx              | 辅助 | 任务规范化对话框                                                                                                                                                                                                                          | ✅    |
| KanbanMarkdown.tsx                   | 辅助 | 安全 Markdown 渲染（GFM + CodeBlock + XSS 白名单 + 可折叠）                                                                                                                                                                               | ✅    |
| KanbanDiagnosticsSection.tsx         | 辅助 | 任务诊断信息展示                                                                                                                                                                                                                          | ✅    |
| KanbanEventTimeline.tsx              | 辅助 | 单任务事件时间线                                                                                                                                                                                                                          | ✅    |
| KanbanTaskExecutionTraceSection.tsx  | 辅助 | 任务 Drawer 内嵌 ExecutionTraceTimeline（lazy 折叠，sessionId=task_id，showEvalCase=false——kanban 无 Chat 记录，保存评测用例无意义；taskStatus=running 时 pollMs 实时刷新 trace）                                                         | ✅    |
| BoardActivityFeed.tsx                | 核心 | Board 级活动流（filter pills + auto-follow + 实时追加）                                                                                                                                                                                   | ✅    |
| kanban-styles.ts                     | 辅助 | 共享样式常量                                                                                                                                                                                                                              | ✅    |

## 状态流转判定与确认

服务端 move 守卫（终态只能归档、草稿池只能去 backlog / ready / archived、审核态不可手动进出）由 `kanban-transitions.ts` 镜像，`resolveMoveIntent` 是唯一判定点：

- `retry`：失败 → 就绪。服务端不允许手动 move 出终态，走 `POST /kanban/tasks/{id}/retry`（重置重试预算与错误，保留历史尝试供 Agent 参考）；先确认。
- `archive`：归档先确认；批量归档在工具栏原位确认。
- `blocked`：服务端必然以 409 拒绝的流转，拖拽落点直接拦下并提示，不发请求；批量拖拽里被拦下的卡片合并成一次提示。
- `move`：其余流转直接调用 `moveTask`；`deps_unmet` 仍走强制放行确认，其余失败一律提示本地化文案。

## Stale Write Guard（乐观 UI 防冲突）

`KanbanBoardView` 内置 `pendingUserWrites` ref（`Map<taskId, { targetStatus, previousStatus, ts }>`）解决 SSE 推送 reload 与用户拖拽的竞态覆盖问题：

1. **乐观更新** — 用户拖拽后立即更新本地 `tasks` 状态，无需等待 API 响应
2. **Pending Guard** — `fetchTasks` 合并服务端数据时，对 pending 中的 task 保留用户设定的 `targetStatus`，阻止 SSE reload 覆盖
3. **成功确认** — `moveTask` API 成功后移除 pending 条目，下次 reload 正常同步
4. **失败回滚** — API 失败时恢复 `previousStatus` 并 toast 提示
5. **超时安全阀** — 5s 后自动清除 pending 条目，防止泄漏

## Chat ↔ Board 会话过滤

- `KanbanBoardView` 读取 URL `?source_chat=`，REST `listTasks` 带 `source_chat_id` 过滤
- `KanbanBoardView` 读取 URL `?status=`，`listTasks` 带 `status` 过滤（`activeStatusFilter` 校验合法状态后统一驱动 UI 过滤条与请求，非法值不生效）
- `KanbanSection` 深链 `?source_chat=&board_id=` 时自动进入 Board 视图（非 Board 列表）；`?status=` 无 `board_id` 时智能选择首个含该状态任务的 board（Fleet Pending KPI 直达）；深链（`board_id`/`status`）无视 project filter 全量拉取 board，确保跨项目待审任务可达，浏览模式（无深链参数）保持 project scope
- Chat 卡片与 Drawer 链接经 `buildKanbanBoardDeepLink`（`@/lib/kanban/kanbanChatBoard.ts`）统一生成

## API 客户端映射（`@/services/kanban.ts`）

| UI 组件                                     | 主要 API                                                    |
| ------------------------------------------- | ----------------------------------------------------------- |
| `KanbanBoardView` / DnD                     | `listTasks`、`moveTask`、`retryTask`、`bulkAction`          |
| `KanbanSpecifyDialog`                       | `specifyTask`（dryRun）→ `applySpec`                        |
| `KanbanDecomposeDialog`                     | `decomposeTask` → `applyDecompose`                          |
| `RaceSection`                               | `raceEstimate` → `raceStart` → `raceLanes` → `raceDecide`   |
| `KanbanPipelineWizard`                      | `listPipelines`、`getPipelineDetail`、`instantiatePipeline` |
| `KanbanDiagnosticsSection`                  | `getTaskDiagnostics`                                        |
| `KanbanEventTimeline` / `BoardActivityFeed` | `listEvents`、`listBoardEvents`、`addComment`               |
| `KanbanGraphView`                           | `listBoardEdges`、`listDependencies`                        |

## 模块依赖

- `@/services/kanban` — `/api/v1/kanban/*` 客户端（Board/Task/Specify/Decompose/Pipeline）
- `@dnd-kit/core` — 拖拽基础设施（传感器 / 碰撞检测 / DragOverlay）
- `@/components/features/app-shell/confirm-dialog` — 通用确认弹窗
- `@/hooks/agent/useAgentName` — 智能体名称映射
- `next-intl` — 国际化（`kanban` namespace；`status.runningWithLimit`、`status.verifying`、`staleRunningCount` 六语言 en/zh/de/ko/ja/zh-TW）

## Completion intent UI

- `KanbanTaskCard` / `KanbanTaskDrawerDetails`：`metadata.completion_intent` 且 `status=running` 时显示 `kanban.status.verifying`（验收中），替代 progress_note
- `KanbanBoardView`：`board_summary.stale_running_count > 0` 时显示红色 pill（`kanban.staleRunningCount`）
- `KanbanBoardView` stats bar：running 列显示 `kanban.status.runningWithLimit`（`执行中: {count}/{limit}`，limit 取自 `board.settings.max_concurrent_tasks`），并发占满时用户可直接判断 ready 任务在排队
