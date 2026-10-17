# progress-steps/

## 架构概述

Agent 执行进度步骤 UI：折叠/展开 Task Steps 树、多态 step 渲染。

## 文件清单

| 文件                           | 地位 | 职责                                                                                     | I/O/P                          |
| ------------------------------ | ---- | ---------------------------------------------------------------------------------------- | ------------------------------ |
| `ProgressSteps.tsx`            | 核心 | 进度步骤树与折叠面板（`data-testid=progress-steps-toggle/panel` 供 Chrome E2E 稳定定位）；撤销提示卡发出的展开事件在撤销入口落在被折叠的中段时一并展开中段 | ✅                             |
| `utils.ts`                     | 辅助 | 步骤标题（`@/lib/humanize` SSOT）                                                        | ✅                             |
| `treeUtils.ts`                 | 辅助 | progressSteps 树构建；`foldRoots` 是折叠规则 SSOT（顶层步骤超过 8 个时保留前 2 个与后 3 个，中段折叠；渲染与展开事件共用） | ✅                             |
| `toolIcons.tsx`                | 辅助 | 步骤图标与 agent 主题色                                                                  | ✅                             |
| `ArchiveRestoreStepAction.tsx` | 组件 | 归档恢复步骤操作                                                                         | ✅                             |
| `ArchiveRestoreResultChip.tsx` | 组件 | 归档恢复结果 chip                                                                        | ✅                             |
| `SkillManageBatchRollbackAction.tsx` | 组件 | skill_manage 成功批次撤销（调用 `/skill-optimization/mutations/{id}/rollback`）；服务端 409 的 `detail.code` 各有专属提示（`batch_already_consumed` 已撤销、`batch_superseded` 同一技能之后又被修改、`skill_missing` 技能已删除、`compensation_failed` 补偿失败），其余失败给通用提示，不暴露服务端英文 | ✅                             |
| `skillManageBatch.ts`          | 辅助 | 读取 step `skill_mutation_batch_id`（server SSE enrich）；`nodeHasSkillManageUndo` 判断步骤或其子步骤是否带撤销入口 | ✅                             |
| `useScrollbarStyles.ts`        | 辅助 | 展开面板滚动条样式                                                                       | ✅                             |
| `StepDetailModal.tsx`          | 组件 | 步骤详情下钻弹窗（查看出入参、诊断建议、stdout 终端流与 Raw JSON）                       | ✅                             |
| `renderers/`                   | 目录 | 步骤叶子渲染（终端、代码、evicted drawer 等）                                            | [_ARCH.md](renderers/_ARCH.md) |
| `__tests__/`                   | 测试 | ProgressSteps guardrail_blocked Badge、utils linkify、ArchiveRestore、SkillManageBatchRollbackAction（成功刷新与计数提示、按 `detail.code` 选择的 5 类错误提示（已撤销 / 补偿失败 / 被较新批次覆盖 / 技能已删除 / 通用）× 中英、重复确认只发一次请求、取消不请求）、ProgressSteps.undoReveal（撤销提示展开事件：折叠中段与嵌套子步骤的撤销入口被展开，已在末尾可见的长回合不展开，短回合与其他消息不受影响）单测 | —                              |

## 依赖

- `@/store/useChatStore` — `updateMessages`（immer updater，禁止误用 `setMessages`）
- `@/lib/humanize` — ProgressSteps 步骤标题 SSOT（`getStepTitle` 第四参 `tHumanize`）
- `@/store/chat/messageStream/handlers/statusStreamProgressSteps.ts` — STATUS progress step reducer

## 约束

- 可变 store 更新必须使用 `updateMessages`，与 stream handlers 一致。
