# Kanban 看板 UI 模块

多任务持久化看板前端组件集——批量提交任务、拖拽排列、自动调度执行。基于 `@dnd-kit/core` 实现跨平台（鼠标/触屏/键盘）拖拽，支持批量操作（卡片勾选框 / Ctrl·Shift 点选）和终态确认弹窗。

## 文件清单

| 文件                                 | 地位 | 职责                                                                                                                                                                                                                                      | I/O/P |
| ------------------------------------ | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| KanbanBoardView.tsx                  | 核心 | 看板主视图的组装层（列布局 + DnD 上下文 + tab 切换 + 抽屉 / 向导 / 重规划入口）；数据、移动、选择、泳道、新增表单分别由 `useKanbanBoardData` / `useKanbanMoveTask` / `useKanbanSelection` / `useKanbanLanes` / `useKanbanAddTask` 持有，标题、统计、筛选提示条、视图切换、列底部新增入口、移动确认框是独立组件；删除 / 回收 / 重试 / 归档经 `useKanbanTaskActionConfirm` 统一确认，卡片、抽屉、拖拽的状态流转统一走它的 `requestMove`；移动失败只提示本地化文案，不透出服务端原文 | ✅    |
| useKanbanBoardData.ts | 核心 | 看板数据层 hook：任务 / 汇总 / 依赖边的拉取与 30s 轮询；`kanban-task-updated` / `app_resync_required` 事件合并成一次延迟刷新；用户写入保护（刚拖动的任务 5 秒内不被服务端旧数据覆盖） | ✅ |
| useKanbanMoveTask.ts | 核心 | 看板任务移动 hook：乐观更新 + 失败回滚 + 依赖未满足时的强制晋升确认 + 多卡批量移动（经 `runBulkAction` 分段请求；被拒的卡片回滚后交回调用方保持选中；强制晋升确认只属于单卡流程）；写入保护通过 `markPendingWrite` / `clearPendingWrite` 登记 | ✅ |
| useKanbanSelection.ts | 核心 | 多选状态 hook：点选 / Shift 区间 / Esc 清除；选中集合只含列里看得见的任务（被删除、归档或被责任筛选藏起来即退出）；换看板归零；Esc 已被菜单或对话框消费（`defaultPrevented`）时不清除 | ✅ |
| kanban-selection.ts | 核心 | 多选与泳道规则纯逻辑：泳道分组、一列此刻是否按泳道渲染、列内可见卡片顺序、`applyTaskClick`；Shift 区间限定在锚点所在的列，与列渲染共用同一套泳道规则 | ✅ |
| useKanbanLanes.ts | 辅助 | Running 列「按 Agent 分泳道」开关（localStorage）与泳道折叠状态 | ✅ |
| KanbanBoardHeader.tsx | 辅助 | 看板标题行（返回 / 名称 / 模板创建 / 批量规范化 / 重规划 / 泳道开关 / 刷新），只展示与回调 | ✅ |
| KanbanBoardStats.tsx | 辅助 | 各状态计数条（Running 显示 `count/limit` 并发占用）、等待过久与疑似卡死提示、按 Agent 的任务分布 | ✅ |
| KanbanViewControls.tsx | 辅助 | 视图切换标签（board / graph / activity）+ 看板视图下的责任人筛选，受控组件 | ✅ |
| KanbanFilterBanners.tsx | 辅助 | URL 带入的「来源会话 / 状态」筛选提示条，带一键清除 | ✅ |
| KanbanColumnAddFooter.tsx | 辅助 | Triage / Ready 列底部的新增入口，展开后是内联新增表单 | ✅ |
| KanbanMoveConfirmDialogs.tsx | 辅助 | 「依赖未满足，强制晋升」与「确认移动到该列」两个确认框，只渲染 | ✅ |
| KanbanReplanDialog.tsx | 辅助 | DAG 计划修订的可视化差异弹窗（新增 / 修改 / 移除的任务与依赖边，提交前做不变量检查） | ✅ |
| KanbanDndComponents.tsx              | 核心 | DnD 渲染（KanbanDropColumn + DraggableTaskCard + Running 泳道 + Drawer 入口；卡片自身登记为 dnd-kit activator，卡片内按钮与菜单的 Enter/Space 不会被劫持成键盘拖拽；卡片左上角的勾选框与 Ctrl/Shift 点选走同一条选择路径，悬停 / 聚焦 / 触屏显现、已有选中项时所有卡片常显，其手势经 `ISOLATE_FROM_CARD` 隔离，不起拖拽也不开抽屉；卡片包装层是 `touch-action: manipulation` 且圆角与卡片本体一致，触屏滑动留给页面滚动，长按才拖拽；屏幕阅读器读到的角色描述是本地化的「可拖动项」）                                                                                                                                                             | ✅    |
| useKanbanDnD.ts                      | 核心 | 拖拽状态管理 hook（传感器：鼠标位移 8px / 触屏长按 250ms / 键盘，不用 `PointerSensor`；事件/终态确认；服务端必拒的流转在落点拦下并提示，批量拖拽只搬能直接流转的卡片，被拦下的合并成一次提示；屏幕阅读器的键盘操作说明与实时播报经 `useDndAccessibility`，念任务标题与本地化列名，不念任务 id 和状态枚举；被拾起的卡片在多选之中时，卡片名后附「已选 n 项」，让读屏用户知道放下会一起移动）                                                                                                                                                                                               | ✅    |
| useKanbanAddTask.ts                  | 辅助 | 任务内联创建表单状态 hook（含 agent/model override 状态）；标题、描述或验收标准被服务端风控拦下（HTTP 400 `risk_held`）时，只有 `apiRequest` 的统一风控提示，表单保留已输入的文字，不另弹「创建失败」提示                                                                                                                                                                                 | ✅    |
| KanbanTaskCard.tsx                   | 核心 | 单任务卡片渲染（首屏决策帧要素/推荐动作微条/状态/进度；操作入口为 KanbanTaskCardActions；附件 badge 点击打开 Drawer；展开详情交给 KanbanTaskCardDetails 渲染、useKanbanTaskCardDetails 持有数据）                                                                                                                                              | ✅    |
| KanbanTaskCardDetails.tsx            | 辅助 | 任务卡片展开后的详情面板（依赖 / 被依赖 / 运行记录 / 事件时间线 / 评论输入），只渲染 `useKanbanTaskCardDetails` 交来的数据，自身无状态 | ✅    |
| useKanbanTaskCardDetails.ts          | 辅助 | 卡片展开详情的数据层 hook：每次展开才取运行记录、事件与依赖，失败给出本地化提示；依赖增删与评论成功后更新本地列表并通知看板刷新；评论被服务端风控拦下时只有统一风控提示，输入框保留文字 | ✅    |
| KanbanTaskCardActions.tsx            | 辅助 | 卡片单一操作菜单（详情 / Specify / Decompose / 状态流转 / 回收 / 删除，回收与删除只发起确认请求；失败任务的「就绪」入口显示为「重试」）；触发器常驻 DOM，桌面悬停或键盘聚焦显现、触屏常显（`REVEAL_ON_HOVER`）；触发器与 portal 菜单上的指针手势不冒泡给 dnd 卡片（否则按下起拖拽、双击开抽屉；隔离属性来自 kanban-card-gestures） | ✅    |
| kanban-card-gestures.ts              | 辅助 | `ISOLATE_FROM_CARD`：卡片内控件（菜单触发器与 portal 菜单、勾选框）的手势隔离属性，鼠标按下 / 触摸按下 / 点击 / 双击不冒泡给 dnd 卡片，按下类事件与传感器激活事件一一对应（契约测试兜底）；附件徽标同样展开 | ✅    |
| KanbanTaskActionConfirm.tsx          | 辅助 | 删除 / 回收 / 重试 / 归档的确认对话框与 `useKanbanTaskActionConfirm` 状态 hook：由看板视图统一持有，卡片菜单、抽屉、拖拽只发起请求；`requestMove` 按 `resolveMoveIntent` 分流（重试与归档先确认，其余直接流转）；文案交代后果（删除连同运行记录一并清除、等待它的任务可能变为就绪并自动开跑；回收会停止执行中的 Agent 并回到就绪；重试会再次消耗模型额度，且失败后已继续推进的下游任务不会重跑；归档后任务离开看板且无法恢复）；关闭动画期间保留任务标题，文案不闪空 | ✅    |
| useKanbanTaskActions.ts              | 辅助 | 回收 / 删除 / 重试 / 归档的执行函数：确认后调 API、刷新列表、给出本地化提示（失败不透出服务端原文）；归档复用看板的乐观移动 | ✅    |
| kanban-transitions.ts                | 核心 | 状态流转的单一判定点：`isServerMoveAllowed(from, to)` 读取共享契约 `shared/config/kanban_move_guard.json`（服务端守卫的镜像，含「原地不动」；服务端契约测试用真实 move 接口逐格核对，守卫改了而表没改会让测试失败）；`resolveMoveIntent(from, to)` 在它之上返回 move / retry / archive / blocked；`moveLabelKey` 给出入口文案 key（失败 → 就绪显示「重试」）。卡片菜单、抽屉、拖拽、批量条共用 | ✅    |
| KanbanTaskDrawer.tsx                 | 辅助 | 任务详情抽屉面板入口（编排 hook 与子组件）                                                                                                                                                                                                | ✅    |
| useKanbanTaskDrawer.ts               | 辅助 | 抽屉面板状态管理 hook（数据加载/操作处理/计算属性）；评论与验收标准被服务端风控拦下时只有统一风控提示，输入保留，不另弹保存失败提示                                                                                                                                                                                       | ✅    |
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
| KanbanBulkActionBar.tsx              | 辅助 | 批量操作工具栏：「移至」「改派」是 Radix 下拉菜单，渲染在 portal 里，不被看板的横向滚动裁剪；条悬浮在全局触发器行之上，窄屏收成纯图标按钮（带 aria-label）；归档与删除都在原位二次确认，同一时刻只开一个；「移至」只列出至少对一个选中任务可达的目标，选中任务全为终态 / 审核态时整个入口隐藏；部分失败时只让失败的任务继续保持选中；请求与结果提示由 `kanban-bulk` 的 `runBulkAction` 负责 | ✅    |
| kanban-bulk.ts                       | 辅助 | `runBulkAction`：批量请求与结果提示的唯一出口，批量工具栏与批量拖拽共用；按每段至多 100 个 id 顺序请求（等于服务端 `task_ids` 的单次上限；归档清理与 completed 合并由服务端放到后台，请求只做状态流转，毫秒级，不必再把分段压小）；请求本身带 `silent`，失败只由汇总提示报一次，不叠全局请求的原始报错与只重放最后一段的重试按钮；没有任务时什么都不发、不提示；所有段合并给一条汇总提示，返回未成功的任务 id；中途某段失败时其后未发送的 id 也算未成功，只有首段就失败才返回 null | ✅    |
| KanbanGraphView.tsx                  | 辅助 | 任务依赖 DAG 可视化（含 running 节点脉冲 / failed 节点抖动动画；依赖连线按父任务状态着色——已完成为 emerald 实线，阻塞 / 失败为红色虚线，小地图同色，颜色取主题变量或带回退的 Tailwind 色阶，不包 `hsl()`）                                                                                                                                                                          | ✅    |
| KanbanPipelineWizard.tsx             | 辅助 | 流水线模板创建向导（支持 repeat_for fan-out 模板的 multi-select 动态并行任务创建）                                                                                                                                                        | ✅    |
| KanbanDecomposeDialog.tsx            | 辅助 | AI 任务分解对话框                                                                                                                                                                                                                         | ✅    |
| KanbanSpecifyDialog.tsx              | 辅助 | 任务规范化对话框                                                                                                                                                                                                                          | ✅    |
| KanbanMarkdown.tsx                   | 辅助 | 安全 Markdown 渲染（GFM + CodeBlock + XSS 白名单 + 可折叠）                                                                                                                                                                               | ✅    |
| KanbanDiagnosticsSection.tsx         | 辅助 | 任务诊断信息展示                                                                                                                                                                                                                          | ✅    |
| KanbanEventTimeline.tsx              | 辅助 | 单任务事件时间线                                                                                                                                                                                                                          | ✅    |
| KanbanTaskExecutionTraceSection.tsx  | 辅助 | 任务 Drawer 内嵌 ExecutionTraceTimeline（lazy 折叠，sessionId=task_id，showEvalCase=false——kanban 无 Chat 记录，保存评测用例无意义；taskStatus=running 时 pollMs 实时刷新 trace）                                                         | ✅    |
| BoardActivityFeed.tsx                | 核心 | Board 级活动流（filter pills + auto-follow + 实时追加）                                                                                                                                                                                   | ✅    |
| kanban-styles.ts                     | 辅助 | 共享样式常量（状态 / 优先级 / 事件徽标样式、看板列顺序 `STATUS_COLUMNS`、时间格式化） | ✅    |

## 状态流转判定与确认

服务端 move 守卫（终态只能归档、草稿池只能去 backlog / ready / archived、审核态不可手动进出）的允许表放在 `shared/config/kanban_move_guard.json`，`kanban-transitions.ts` 读取它，`resolveMoveIntent` 是唯一判定点。服务端 `tests/api/kanban/test_move_guard_contract.py` 用真实 move 接口逐格核对这张表，改了守卫而没改表会让测试失败：

- `retry`：失败 → 就绪。服务端不允许手动 move 出终态，走 `POST /kanban/tasks/{id}/retry`（重置重试预算与错误，保留历史尝试供 Agent 参考）；先确认。
- `archive`：归档先确认；批量归档在工具栏原位确认。
- `blocked`：服务端必然以 409 拒绝的流转，拖拽落点直接拦下并提示，不发请求；批量拖拽里被拦下的卡片合并成一次提示。
- `move`：其余流转直接调用 `moveTask`；`deps_unmet` 仍走强制放行确认，其余失败一律提示本地化文案。

批量条的「移至」直接用 `isServerMoveAllowed` 过滤目标：只隐藏对整个选择必然全部失败的目标，仍有任务能到达的目标保留，混合选择由服务端逐条返回部分成功；选中任务查不到状态时不过滤。失败任务的恢复只走单卡的「重试」。

## 批量选择

- 点选 / Shift 区间由 `kanban-selection.ts` 与 `useKanbanSelection.ts` 处理：Shift 区间只在锚点所在的列内、按屏幕上实际显示的顺序取（泳道、折叠的泳道与列渲染共用同一套规则），锚点不在该列时退化为点选切换。
- 选中集合只含列里看得见的任务：任务被删除、归档，或被责任筛选藏起来后自动退出选择，批量操作不会作用到看不见的任务。
- `KanbanBulkActionBar` 的批量结果逐条返回；部分失败时只让失败的任务继续保持选中，方便直接重试。
- Esc 清除选择，但已被菜单或对话框用来关闭自己（`defaultPrevented`）的那一下不算。
- 每张卡片左上角有勾选框，与 Ctrl/Cmd 点选、Shift 区间共用 `onTaskSelect` 这一条选择路径：悬停、键盘聚焦、触屏显现，已有选中项时所有卡片常显；Space 切换（Enter 按复选框语义不触发）。这是触屏与键盘用户进入多选的入口。勾选框的描边用完整主色并加 `!`：`globals.css` 里不在 layer 内的 `* { border-color }` 会盖掉普通的 border 色类，不加则未选中的圆圈与底色对比度只有约 1.2:1（浅 / 深主题实测，现为 3.4:1 / 6.7:1）。
- 批量拖拽与批量条的移动走同一条路径（`runBulkAction`，按段请求、逐条结果）：卡片乐观移动，只回滚被拒的，部分失败给一条汇总提示，被拒的卡片保持选中，首段就失败则全部回滚，中途某段失败则其后未发送的卡片与被拒的卡片同样回滚并保持选中；多选拖拽里真正需要移动的只剩一张卡（其余已在目标列）时按单卡处理。单卡拖拽走单任务接口与「强制晋升」确认——那是单卡决策，确认框只有一个槽位，批量路径不弹它；批量接口不接受 `force`，强制晋升只存在于单任务 move 接口。

## 拖拽与触屏手势

- 传感器按设备分开：鼠标位移 8px 起拖，触屏长按 250ms 起拖（长按期间位移超 5px 就取消，交还给页面滚动），键盘由聚焦的卡片自身激活。不使用 `PointerSensor`：它同样接管触屏指针，位移到阈值就起拖拽，卡片上的滑动滚不动看板，还会发出一次移动请求（真实 Chromium 触屏模拟实测）。
- 卡片包装层是 `touch-action: manipulation`：触屏平移留给浏览器，从卡片上起手的滑动用来滚动看板，长按才拖拽；`touch-none` 会让卡片上的任何滑动都失去滚动。
- 手势隔离：卡片内控件（勾选框、菜单触发器与 portal 菜单、附件徽标）展开 `ISOLATE_FROM_CARD`，按下类事件须覆盖鼠标与触屏传感器的激活事件（`onMouseDown`、`onTouchStart`）；键盘传感器只在卡片自身被聚焦时激活，控件内的按键不需要隔离。`__tests__/kanban-card-gestures.test.ts` 读取看板真实传感器核对这一对应，换传感器而没改隔离属性会让测试失败。
- 验证范围：Chromium 触屏模拟（横向滑动滚动看板、纵向滑动滚动页面且都不起拖拽、24px 快滑不起拖拽、长按起拖并能放进相邻列、从勾选框与菜单触发器长按不起拖拽）与桌面鼠标（位移不足 8px 不起拖拽、较长位移起拖并发出一次移动）。iOS Safari、Android 真机、手写笔与读屏软件没有验证；长按期间浏览器的长按菜单由 dnd-kit 传感器阻止、起拖时清除文本选择（读自 `@dnd-kit/core` 源码，真机没有验证）。另外，无头 Chromium 在页面加载后约 2 秒内会丢掉触屏滚动手势（从空白列区域起手也一样，闲置 6 秒后正常），与传感器无关，自动化走查要等页面稳定后再测。

## Stale Write Guard（乐观 UI 防冲突）

`useKanbanBoardData` 持有 `pendingUserWrites` ref（`Map<taskId, { targetStatus, previousStatus, ts }>`），`useKanbanMoveTask` 通过 `markPendingWrite` / `clearPendingWrite` 登记与清除，解决 SSE 推送 reload 与用户拖拽的竞态覆盖问题：

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
- `KanbanBoardStats`：`board_summary.stale_running_count > 0` 时显示红色 pill（`kanban.staleRunningCount`）
- `KanbanBoardStats`：running 列显示 `kanban.status.runningWithLimit`（`执行中: {count}/{limit}`，limit 取自 `board.settings.max_concurrent_tasks`），并发占满时用户可直接判断 ready 任务在排队
