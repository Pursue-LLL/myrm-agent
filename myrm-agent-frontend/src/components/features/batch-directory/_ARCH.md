# batch-directory/

## 架构概述

批量目录并行项目（同一个 Prompt × N 个目录）的列表页与详情页 UI，对接 [`services/batch-directory.ts`](../../../services/batch-directory.ts)。`app/batch-directories/page.tsx` 与 `[projectId]/page.tsx` 只做装配，状态与动作在本目录的 hooks 里，展示在各区块组件里。

## 文件清单

| 文件                         | 地位 | 职责                                                                                                                                                   | I/O/P |
| ---------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `batchProjectModel.ts`       | 逻辑 | 列表 / 详情共用纯函数：`formatDateTime`、`batchProgressPercent`、`deriveProjectFlags`（运行 / 暂停 / 终态 / 待审核数 / 可整体重试）、`isTaskRetryable` | ✅    |
| `BatchStatusBadges.tsx`      | 组件 | 项目 / 任务状态到文案、图标与色调的唯一映射（`BATCH_TONE`）；未知状态回退到草稿 / 待处理样式；危险色调用 `text-destructive-text`                       | ✅    |
| `BatchConfirmAlert.tsx`      | 组件 | 触发元素 + 二次确认弹窗，开合由弹窗自身管理；`destructive` 时确认按钮用实心 `bg-destructive`                                                           | ✅    |
| `useBatchProjects.ts`        | 辅助 | 列表数据层：加载、聚合统计、取消 / 删除并在成功后重新拉取，失败统一 toast                                                                              | ✅    |
| `BatchProjectStats.tsx`      | 组件 | 列表页顶部四张统计卡（项目数 / 运行中 / 已完成任务 / 失败任务）                                                                                        | ✅    |
| `BatchProjectTable.tsx`      | 组件 | 列表页项目表；运行中只能取消，其余只能删除，二者都需二次确认                                                                                           | ✅    |
| `BatchProjectCreateCard.tsx` | 组件 | 创建向导卡片（名称、提示词、目录、看板、并发、产物匹配、通知与审批开关）；状态全部来自 `useBatchProjectCreate`                                         | ✅    |
| `BatchDirectoryPicker.tsx`   | 组件 | 目录选择器：路径条 + 上一级 / 刷新 + 可勾选的子目录列表；整行点击切换勾选，行尾箭头进入子目录                                                          | ✅    |
| `useBatchProjectCreate.ts`   | 辅助 | 创建向导状态层：表单、看板选项、校验与提交；向导收起后保留表单与已选目录，创建成功才清空；提示词被风控拦下时只显示统一风控提示                         | ✅    |
| `useDirectoryBrowser.ts`     | 辅助 | 目录浏览与多选状态：当前目录、条目、已选集合（跨目录浏览保留）、浏览 / 上一级 / 勾选 / 重置                                                            | ✅    |
| `useBatchProjectDetail.ts`   | 辅助 | 详情数据层：解析路由 `projectId`、加载详情、非终态时每 10 秒自动刷新；`refresh` 在拉取完成后才 resolve                                                 | ✅    |
| `useBatchProjectActions.ts`  | 辅助 | 详情动作层：取消 / 重试 / 重跑 / 暂停 / 恢复 / 全部通过共用 `run(key)` 与相互独立的忙碌标志，另有单任务重试与删除（成功后回列表）                      | ✅    |
| `BatchProjectHeader.tsx`     | 组件 | 详情页头部：返回按钮、项目名、状态徽标、项目 id、动作栏；窄屏上下堆叠                                                                                  | ✅    |
| `BatchProjectToolbar.tsx`    | 组件 | 动作栏：按项目状态显示可用动作，互斥动作在对方进行时禁用；影响面大的动作先二次确认                                                                     | ✅    |
| `BatchProjectOverview.tsx`   | 组件 | 「进度概览」（总数 / 完成 / 失败 + 进度条）与「运行配置」（看板、并发、Agent、通知、创建 / 结束时间、耗时）两张卡片                                    | ✅    |
| `BatchProjectScope.tsx`      | 组件 | 提示词、产物匹配规则、目录清单（失败目录高亮）与缺失产物目录卡片；提示词 / 规则为空时不渲染                                                            | ✅    |
| `BatchTaskTable.tsx`         | 组件 | 任务表：状态、目录、结果摘要；失败、已归档或产物缺失的任务可单独重试，整体重试 / 重跑进行中时锁定                                                      | ✅    |

## 测试

`__tests__/` 下 `batchTestKit.tsx` 提供共用的 mock、夹具与交互 helper；`BatchDirectoriesPage`、`BatchProjectCreateWizard`（含目录选择器单击勾选回归）、`BatchProjectDetailPage`（含轮询）、`BatchProjectActions`（动作可见性、互斥、成功 / 失败）、`BatchTaskRetryAndDelete`、`BatchStatusBadges`、`batchProjectModel` 各一份测试文件。

## 依赖

- `@/services/batch-directory`、`@/components/primitives/*`、`@/hooks/shared/useToast`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
