# progress-steps/

## 架构概述

Agent 执行进度步骤 UI：折叠/展开 Task Steps 树、多态 step 渲染。

## 文件清单

| 文件                           | 地位 | 职责                                                                                     | I/O/P                          |
| ------------------------------ | ---- | ---------------------------------------------------------------------------------------- | ------------------------------ |
| `ProgressSteps.tsx`            | 核心 | 进度步骤面板外壳：展开 / 折叠状态、面板与动画（`slide-up`、`animate-rotate-step` 用 `:global` 声明，子组件共用）、加载中滚动到底、带被 evict 输出的步骤自动展开、详情弹窗（`data-testid=progress-steps-toggle/panel` 供 Chrome E2E 稳定定位）；撤销提示卡发出的展开事件在撤销入口落在被折叠的中段时一并展开中段；折叠摘要与步骤树由下列组件渲染 | ✅                             |
| `CollapsedStepSummary.tsx`     | 组件 | 折叠摘要：最新步骤（有图像分析时取最近一次）的宏观阶段、错误分类徽标与进度；进行中时附带终端最后一行；有被 evict 输出的步骤时保留完整输出入口 | ✅                             |
| `StepTreeList.tsx`             | 组件 | 展开面板的顶层步骤列表：按 `foldRoots` 折叠中段，给出「展开 N 个中间步骤」与「收起」入口 | ✅                             |
| `ProgressStepNode.tsx`         | 组件 | 步骤树节点（递归）：状态圆点、头部、正文（原因、错误框、产出、归档恢复与撤销入口、压缩丢弃清单、终端）与子节点；有子节点的计划节点只显示头部与子节点；`StepNodeContext` 是整棵树共享的渲染上下文 | ✅                             |
| `StepNodeHeader.tsx`           | 组件 | 节点头部行：图标、标题、错误分类与责任方徽标、耗时、详情入口、进度百分比与进度条 | ✅                             |
| `StepErrorPanel.tsx`           | 组件 | 节点错误框：错误原文（链接化）、诊断建议与恢复操作；被拒绝的调用按警告配色 | ✅                             |
| `StepOutput.tsx`               | 组件 | 节点产出：`StepItemsView` 按 items 形态选择渲染器（计划节点与委派工具行不重复渲染），`StepTerminal` 输出终端与被 evict 的完整输出入口 | ✅                             |
| `StepHeading.tsx`              | 组件 | 步骤图标与标题行（agent 徽标、智能降级徽标），展开节点与折叠摘要共用 | ✅                             |
| `StepTimeline.tsx`             | 组件 | 时间线构件：随状态变色的圆点（进行中旋转）与竖向连接线 | ✅                             |
| `stepTone.ts`                  | 辅助 | 步骤「状态 → 颜色」的唯一来源：视觉状态判定与文字色；文字一律用 `text-destructive-text`，填充令牌 `destructive` 只用于背景与边框 | ✅                             |
| `utils.ts`                     | 辅助 | 步骤标题（`@/lib/humanize` SSOT）；外部 agent 委派步骤 `delegation_<agent>_<status\|tool\|session_expired\|session_workspace_changed\|images_not_sent\|turn_limit>`：状态行与「上一轮对话未能延续」「图片没有直接交给该 agent」「已达回合上限」提示由 step_key 本地化，单次工具调用以自身文本行作标题（`isDelegationToolLine` 让 `StepItemsView` 不再把同一行再渲染一遍）；`getDisplayStatus`：步骤的展示状态，被拒绝的调用中「用户拒绝 / 审批超时」是一次决定而非故障，按警告（琥珀色）展示，策略拦截等仍为错误，实时流与重载历史同一规则；`getStatusLabelKey`：步骤结果的措辞（拒绝类写「用户已拒绝 / 审批超时」，其余取 `progressSteps.statusLabels`，六种语言，不向用户显示状态码）；`WARNING_NOTICE`：警告色的提示框、文字、分隔线与徽标样式。三者由步骤树各组件、`StepDetailModal`、`EvidenceStageHUD` 共用；`handleLinkClick`：在新标签页打开链接，`StepItemsView` 的文本与链接项点击由它处理 | ✅                             |
| `treeUtils.ts`                 | 辅助 | progressSteps 树构建；`foldRoots` 是折叠规则 SSOT（顶层步骤超过 8 个时保留前 2 个与后 3 个，中段折叠；渲染与展开事件共用） | ✅                             |
| `toolIcons.tsx`                | 辅助 | 步骤图标与 agent 主题色                                                                  | ✅                             |
| `ArchiveRestoreStepAction.tsx` | 组件 | 归档恢复步骤操作                                                                         | ✅                             |
| `ArchiveRestoreResultChip.tsx` | 组件 | 归档恢复结果 chip                                                                        | ✅                             |
| `SkillManageBatchRollbackAction.tsx` | 组件 | skill_manage 成功批次撤销（调用 `/skill-optimization/mutations/{id}/rollback`）；服务端 409 的 `detail.code` 各有专属提示（`batch_already_consumed` 已撤销、`batch_superseded` 同一技能之后又被修改、`skill_missing` 技能已删除、`compensation_failed` 补偿失败），其余失败给通用提示，不暴露服务端英文 | ✅                             |
| `skillManageBatch.ts`          | 辅助 | 读取 step `skill_mutation_batch_id`（server SSE enrich）；`nodeHasSkillManageUndo` 判断步骤或其子步骤是否带撤销入口 | ✅                             |
| `useScrollbarStyles.ts`        | 辅助 | 展开面板滚动条样式                                                                       | ✅                             |
| `StepDetailModal.tsx`          | 组件 | 步骤详情下钻弹窗（查看出入参、诊断建议、stdout 终端流与 Raw JSON）；结果徽标与诊断框随展示状态着色并用界面语言措辞，被拒绝的调用与步骤列表同为琥珀色 | ✅                             |
| `renderers/`                   | 目录 | 步骤叶子渲染（终端、代码、evicted drawer 等）                                            | [_ARCH.md](renderers/_ARCH.md) |
| `__tests__/`                   | 测试 | loop guard 步骤标题（`loop_guard_warn*` / `loop_guard_break` 在 6 种语言里都取自语言包、不回落成原始 key，`loop_guard_break` 与它的 toast 在 6 种语言里都不声称运行已停止，`tool_stuck_paused` 暂停标题同样取自语言包，`utils.loopGuardTitle.test.ts`；真实 `ProgressSteps` 展开后显示这两类步骤的目录文案而不是原始 key，`ProgressSteps.loopGuardSteps.test.tsx`）、ProgressSteps guardrail_blocked Badge、拒绝类调用的语气（ProgressSteps.refusalTone：徽标、原因与诊断提示同色；utils.displayStatus：展示状态与结果措辞；StepDetailModal：结果徽标与诊断框）、utils linkify、ArchiveRestore、SkillManageBatchRollbackAction（成功刷新与计数提示、按 `detail.code` 选择的 5 类错误提示（已撤销 / 补偿失败 / 被较新批次覆盖 / 技能已删除 / 通用）× 中英、重复确认只发一次请求、取消不请求）、ProgressSteps.undoReveal（撤销提示展开事件：折叠中段与嵌套子步骤的撤销入口被展开，已在末尾可见的长回合不展开，短回合与其他消息不受影响）、外部 agent 委派步骤（utils.delegation：状态行 / 连续性提示 / 工具行标题与含下划线的 agent 名；ProgressSteps.delegation：工具行只出现一次、状态行正文保留、失败原因仍显示）、步骤各组件（`stepTone`：状态判定与文字色；`StepTimeline` / `StepHeading` / `StepNodeHeader` / `StepErrorPanel` / `StepOutput` / `CollapsedStepSummary` / `ProgressStepNode` / `StepTreeList`：各自的取舍、文字色令牌与交互；`ProgressSteps.shell`：展开收起、折叠摘要选取、滚动、evict 自动展开、折叠入口、详情弹窗与全局动画类声明；`progressStepsKit` / `progressStepsStubs` 为共用夹具；`utils.handleLinkClick`）单测 | —                              |

## 依赖

- `@/store/useChatStore` — `updateMessages`（immer updater，禁止误用 `setMessages`）
- `@/lib/humanize` — ProgressSteps 步骤标题 SSOT（`getStepTitle` 第四参 `tHumanize`）
- `@/store/chat/messageStream/handlers/statusStreamProgressSteps.ts` — STATUS progress step reducer

## 约束

- 可变 store 更新必须使用 `updateMessages`，与 stream handlers 一致。
