# cron/

## 架构概述

定时任务（Cron）管理界面，对接 server cron API。含 Blueprint 模板库，提供模板化快速创建能力。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `cron-blueprints.ts` | 数据/逻辑 | 蓝图 catalog 自 API `/cron/blueprints` 加载（含 slot `optional`；无离线 fallback）；`buildBlueprintCreatePayload` 仅走 `POST /blueprints/fill` SSOT，并透传 fill 返回的 `job_defaults`（job_type/session_target/monitor/failure_alert/pre_condition）；`buildScheduleFromSlots` 仅用于 preview；`blueprintSnakeToCamel`/`resolveBlueprint*Key` i18n 键映射、`loadBlueprints()` | ✅ |
| `BlueprintCatalog.tsx` | 组件 | 模板卡片网格（API catalog + 加载失败重试；`useLocale()` 展示 title/description，slot 标签走 locale JSON） | ✅ |
| `BlueprintInlineFill.tsx` | 组件 | 内联模板填写表单（`useLocale()` 解析 API 标题；CronJobCreateDialog 内使用），含 delivery channel 选择 | ✅ |
| `BlueprintFillDialog.tsx` | 组件 | 模板参数填写弹窗（`useLocale()` + typed slots + delivery channel），用于 CronJobList 空状态 | ✅ |
| `ActiveHoursEditor.tsx` | 组件 | 活跃时段（active hours）可视化编辑器 | ✅ |
| `AllowedRootsEditor.tsx` | 组件 | Cron 允许工作目录 roots 列表编辑 | ✅ |
| `CapabilityEditor.tsx` | 组件 | Cron Agent 能力/工具约束编辑 | ✅ |
| `CronAdvancedEditors.tsx` | 组件 | 高级选项折叠区（timeout/retry/concurrency） | ✅ |
| `CronDeliveryEditors.tsx` | 组件 | 投递渠道（email/webhook/push）配置编辑器 | ✅ |
| `CronJobCard.tsx` | 核心 | 单条 Cron 任务卡片（状态/下次运行/快捷操作） | ✅ |
| `CronJobCreateDialog.tsx` | 组件 | 创建弹窗（Template/Custom；含 Agent/Shell/Script/Reminder 类型 + delivery） | ✅ |
| `CronJobList.tsx` | 核心 | 任务列表；`?chat_id=` 过滤；排程建议链到 evolutionPending | ✅ |
| `CronMonitorEditors.tsx` | 组件 | 监控/告警阈值编辑 | ✅ |
| `CronPushPoller.tsx` | 组件 | 客户端 push 通知轮询注册（Web Push） | ✅ |
| `CronRunHistory.tsx` | 组件 | 单任务运行历史列表 | ✅ |
| `CronRunItem.tsx` | 组件 | 单次运行记录行（状态/耗时/log 链接） | ✅ |
| `CronStatsBar.tsx` | 组件 | 任务统计摘要条（成功/失败/活跃数） | ✅ |
| `SchedulerHealthBadge.tsx` | 组件 | 调度器存活状态 Badge（绿/黄/红），30s 轮询 GET /cron/scheduler/health | ✅ |
| `CronTriggerEditor.tsx` | 组件 | Cron 触发器编辑（Webhook/Event/System） | ✅ |
| `CronTriggerWebhookDisplay.tsx` | 组件 | Webhook URL/Secret/cURL 展示与复制 | ✅ |
| `CronUsageStats.tsx` | 组件 | Cron 配额/用量统计图表 | ✅ |
| `EditorToggle.tsx` | 辅助 | Simple/Advanced 编辑器模式切换 | ✅ |
| `GlobalRunHistory.tsx` | 组件 | 全局 Cron 运行历史聚合视图 | ✅ |
| `WebhookGuide.tsx` | 组件 | Webhook 触发接入说明与示例 | ✅ |
| `cron-utils.ts` | 辅助 | Cron 表达式解析、格式化与校验纯函数 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
