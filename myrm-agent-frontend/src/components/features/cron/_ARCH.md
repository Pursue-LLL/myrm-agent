# cron/

## 架构概述

定时任务（Cron）管理界面，对接 server cron API。含 Blueprint 模板库，提供模板化快速创建能力。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `cron-blueprints.ts` | 数据/逻辑 | 模板定义（含 defaultDeduplicate）、buildJobPayload、humanizeSchedule、Cron Presets | — |
| `BlueprintCatalog.tsx` | 组件/模块 | 模板卡片网格，支持 maxItems 裁剪 | — |
| `BlueprintInlineFill.tsx` | 组件/模块 | 内联模板填写表单（CronJobCreateDialog 内使用），含 delivery channel 选择 | — |
| `BlueprintFillDialog.tsx` | 组件/模块 | 模板参数填写弹窗（typed slots + delivery channel），用于 CronJobList 空状态 | — |
| `ActiveHoursEditor.tsx` | 组件/模块 | 活跃时段编辑器 | — |
| `AllowedRootsEditor.tsx` | 组件/模块 | Agent 允许根目录编辑器 | — |
| `CapabilityEditor.tsx` | 组件/模块 | 工具能力编辑器 | — |
| `CronAdvancedEditors.tsx` | 组件/模块 | 高级任务编辑器（含 DeduplicateEditor 输出 hash 去重开关） | — |
| `CronDeliveryEditors.tsx` | 组件/模块 | 成功/失败投递渠道编辑器 | — |
| `CronJobCard.tsx` | 组件/模块 | 任务列表卡片（含 incremental monitor / deduplicate badge） | — |
| `CronJobCreateDialog.tsx` | 组件/模块 | 创建弹窗（Template/Custom 双模式 + Cron Presets + delivery channel） | — |
| `CronJobList.tsx` | 组件/模块 | 任务列表（空状态含模板引导） | — |
| `CronMonitorEditors.tsx` | 组件/模块 | 增量监控编辑器 | — |
| `CronPushPoller.tsx` | 组件/模块 | Cron 实时 toast 轮询 | — |
| `CronRunHistory.tsx` | 组件/模块 | 任务详情与编辑器（Delivery 区含 DeduplicateEditor） | — |
| `CronRunItem.tsx` | 组件/模块 | 单次运行记录（delivery skip reason i18n badge） | — |
| `CronStatsBar.tsx` | 组件/模块 | 任务统计条 | — |
| `CronTriggerEditor.tsx` | 组件/模块 | 触发器编辑器 | — |
| `CronUsageStats.tsx` | 组件/模块 | 用量统计 | — |
| `EditorToggle.tsx` | 组件/模块 | 通用开关组件 | — |
| `GlobalRunHistory.tsx` | 组件/模块 | 全局运行历史 | — |
| `WebhookGuide.tsx` | 组件/模块 | Webhook 配置引导 | — |
| `cron-utils.ts` | 组件/模块 | 格式化与 resolveDeliverySkipReasonKey 等工具 | — |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
