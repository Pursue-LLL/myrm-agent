# components/features/system-monitor/

## 架构概述

本地与沙箱系统级可观测与诊断层：因果 Trace 时序、分层健康、智能体诊断、定时任务巡检，以及用量、成本与预算面板组件。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.ts` | 类型 | 因果 Trace 树、分层健康与定时任务巡检的 TypeScript 契约定义 | ✅ |
| `CausalTraceWaterfallView.tsx` | 组件 | 单次请求因果 TraceSpan 树时序瀑布图、阶段耗时占比与元数据属性展开视图 | ✅ |
| `MultiTierHealthBadge.tsx` | 组件 | 组件支撑层 (Component) 与入口网关层 (Ingress) 能力分层健康大盘卡片 | ✅ |
| `AgentDoctorWizard.tsx` | 组件 | 智能体四大失效表象诊断向导、六大断点时序流水与就地重发控制台 | ✅ |
| `AgentDiagnosticCapsule.tsx` | 组件 | 智能体运行异常轻量诊断胶囊，提供异常表象即时提示与向导触发 | ✅ |
| `ProductivityRoiDashboard.tsx` | 组件 | 月度生产力投资回报透视大盘与高频劳务节省工时分类排行看板 | ✅ |
| `SandboxSelfHealButton.tsx` | 组件 | 沙箱卡死一键就地热重启自愈按钮，支持 10 秒倒计时防抖与 Volume 数据完整性保证 | ✅ |
| `InAppDiagnosticModal.tsx` | 组件 | 端内沙箱现场全景诊断打包展示、PII 自动脱敏态势与闪电工单极速提交弹窗 | ✅ |
| `cronDoctorTypes.ts` | 类型 | 定时任务舰队巡检、6 大防御门禁与外科手术式修复类型契约 | ✅ |
| `CronFleetHealthDeck.tsx` | 组件 | 定时任务舰队全景健康体态顶栏胶囊看板与静默故障隐患告警卡片 | ✅ |
| `CronDoctorReportDrawer.tsx` | 组件 | 定时任务隐患详情自查抽屉、修复指引与外科手术式快速治愈执行视窗 | ✅ |
| `unattendedCoverageTypes.ts` | 类型 | 无人值守与多渠道运行事件日志覆盖状态与分片健康 TypeScript 契约定义 | ✅ |
| `UnattendedEventLogCoverageHUD.tsx` | 组件 | 无人值守与多渠道事件日志覆盖全景大盘，呈现 Cron/Channel/Goal/Voice 统一注入与按日分片防无限增长指标 | ✅ |
| `index.ts` | 门面 | 聚合导出模块内所有组件与类型定义 | ✅ |



