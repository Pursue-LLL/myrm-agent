# cron/

## 架构概述

定时任务（Cron）管理界面，对接 server cron API。含 Blueprint 模板库，提供模板化快速创建能力。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `cron-blueprints.ts` | 数据/逻辑 | 蓝图定义 (从 API `/cron/blueprints` 异步加载 + 离线 fallback)、loadBlueprints()、getCachedBlueprints()、fillBlueprintFromServer()、buildJobPayload(t, delivery?)、humanizeSchedule、Cron Presets | — |
| `BlueprintCatalog.tsx` | 组件/模块 | 模板卡片网格，支持 maxItems 裁剪 | — |
| `BlueprintInlineFill.tsx` | 组件/模块 | 内联模板填写表单（CronJobCreateDialog 内使用），含 delivery channel 选择 | — |
| `BlueprintFillDialog.tsx` | 组件/模块 | 模板参数填写弹窗（typed slots + delivery channel），用于 CronJobList 空状态 | — |
| `ActiveHoursEditor.tsx` | 组件/模块 | — | — |
| `AllowedRootsEditor.tsx` | 组件/模块 | — | — |
| `CapabilityEditor.tsx` | 组件/模块 | — | — |
| `CronAdvancedEditors.tsx` | 组件/模块 | — | — |
| `CronDeliveryEditors.tsx` | 组件/模块 | — | — |
| `CronJobCard.tsx` | 组件/模块 | — | — |
| `CronJobCreateDialog.tsx` | 组件/模块 | 创建弹窗（Template/Custom 双模式 + 内联模板填写 + Cron Presets + delivery channel 全模式可用） | — |
| `CronJobList.tsx` | 组件/模块 | 任务列表（空状态含模板引导） | — |
| `CronMonitorEditors.tsx` | 组件/模块 | — | — |
| `CronPushPoller.tsx` | 组件/模块 | — | — |
| `CronRunHistory.tsx` | 组件/模块 | — | — |
| `CronRunItem.tsx` | 组件/模块 | — | — |
| `CronStatsBar.tsx` | 组件/模块 | — | — |
| `SchedulerHealthBadge.tsx` | 组件/模块 | 调度器存活状态 Badge（绿/黄/红），30s 轮询 GET /cron/scheduler/health | — |
| `CronTriggerEditor.tsx` | 组件/模块 | Cron 触发器编辑（Webhook/Event/System） |
| `CronTriggerWebhookDisplay.tsx` | 组件/模块 | Webhook URL/Secret/cURL 展示与复制 |
| `CronUsageStats.tsx` | 组件/模块 | — | — |
| `EditorToggle.tsx` | 组件/模块 | — | — |
| `GlobalRunHistory.tsx` | 组件/模块 | — | — |
| `WebhookGuide.tsx` | 组件/模块 | — | — |
| `cron-utils.ts` | 组件/模块 | — | — |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
