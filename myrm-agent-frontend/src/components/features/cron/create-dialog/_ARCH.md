# create-dialog/

## 架构概述

「创建定时任务」弹窗 Custom 页签的全部实现。弹窗外壳 [`../CronJobCreateDialog.tsx`](../CronJobCreateDialog.tsx) 只管页签、模板流程与创建后的审计面板；表单状态、校验、请求体与各字段区块在本目录。所有可重置字段集中在 `useCronCreateForm` 持有的单个 `draft`，重置只需整体覆盖一次。

## 文件清单

| 文件                           | 地位 | 职责                                                                                                                                                                                          | I/O/P |
| ------------------------------ | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `cronCreateModel.ts`           | 逻辑 | 无 React 的纯逻辑：草稿形状与初值、调度 / 月度执行估算、内容 / 会话 / 时间上限校验、默认任务名（用户填的名称，否则取文本前 30 字；提醒也取其提示词）、前置验证查询、投递与创建请求体          | ✅    |
| `useCronCreateOptions.ts`      | 辅助 | 弹窗打开期间的服务端选项：Shell 是否可用（部署模式）、已连接 IM 渠道、可绑定的工作流模板；任一请求失败都退化为「无该选项」                                                                    | ✅    |
| `useCronPrerequisite.ts`       | 辅助 | 前置验证（是否已手动验证过）的去抖查询：文本停止变化 400 ms 后才查，没有内容时清空结果，查询失败视为无结果；`clear` 供重置使用                                                                | ✅    |
| `useCronCreateForm.ts`         | 辅助 | 弹窗唯一状态源：`draft` + `patch`、派生的调度 / 校验、提交与重置；所选工作流模板有占位符且未填时先弹参数对话框；创建成功进入审计面板，被风控拦下时只有统一风控提示、表单保留                  | ✅    |
| `CronCreateCustomForm.tsx`     | 组件 | Custom 页签装配层：按「跑什么 → 交给谁 → 何时跑 → 哪个会话 → 怎样算跑完」组装各区块，末尾是前置验证门禁卡与取消 / 创建按钮                                                                    | ✅    |
| `CronCreateContentFields.tsx`  | 组件 | 任务类型、名称与随类型切换的内容输入（Agent / 提醒提示词 + 工作流模板、Shell 命令、Python 脚本）；换工作流模板会清空已填的模板参数                                                            | ✅    |
| `CronCreateTargetFields.tsx`   | 组件 | 投递渠道（IM 渠道需要收件人）与 Agent 绑定；两者都只在有可选项时出现                                                                                                                          | ✅    |
| `CronCreateScheduleFields.tsx` | 组件 | 调度类型与输入、人话预览、月度执行估算卡（高频琥珀警示）、周期任务的部署提示；切到单次调度会把会话模式重置为独立会话                                                                          | ✅    |
| `CronCreateSessionFields.tsx`  | 组件 | 会话模式（独立会话 / 对话线程）与默认模型说明；仅周期性 Agent 任务可选会话模式，从对话打开时线程固定为该对话                                                                                  | ✅    |
| `CronCreatePolicyFields.tsx`   | 组件 | 单次运行时间上限（`TimeoutInput`，留空沿用服务端默认，范围外的值禁用创建；提醒没有该输入，切到提醒后不再提交该值，也不再因它禁用创建）与 Agent 任务的验收标准列表（最多 10 条，空描述不提交） | ✅    |

## 测试

`__tests__/createDialogTestKit.tsx` 提供共用的模块 mock、夹具与交互 helper（假时钟来自 `@/test-utils/fakeClock`）；`cronCreateModel` 覆盖纯逻辑，`CronCreateContentAndTarget` / `CronCreateScheduleAndPolicy` 覆盖各字段区块的可见行为，`CronCreateRequest` 断言每种任务提交给 `createJob` 的请求体，`CronCreateOutcome` 覆盖创建结果、失败、关闭与模板页签，`CronCreatePrerequisiteAndWorkflow` 覆盖去抖的前置验证与工作流模板参数流程。

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 同级 [`../CronDeliveryEditors.tsx`](../CronDeliveryEditors.tsx)（渠道文案与收件人判定）、[`../CronPrerequisiteCard.tsx`](../CronPrerequisiteCard.tsx)（门禁卡）、[`../cron-utils.ts`](../cron-utils.ts)（`PILL_TOGGLE_CLASS`、超时解析）
- 父模块 [`../_ARCH.md`](../_ARCH.md)
