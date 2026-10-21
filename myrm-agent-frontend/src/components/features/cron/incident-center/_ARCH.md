# Cron Incident Center & Silent Failure Verification Barrier Suite 架构说明

## 1. 业务目标与核心价值
彻底破除定时任务进程返回 exit 0 假成功但实际未产出任何结果的摸鱼欺骗，以及用户管理海量定时任务时缺乏全局故障总览的严重体验断层。
对标 Hermes v0.21.0 故障回执与现代 GUI 运维中心实践，实现：
1. **全局定时任务事故待办中心 (Cron Incident Center)**：在界面顶部常驻事故警示条，支持事故分类聚合（假成功、配额耗尽、密钥失效、超时、崩溃）、一键单条/批量确认签收 (Ack)、以及一键深链跳转至执行历史进行日志排查；
2. **“假成功”静默失败熔断门禁 (Silent Failure Verification Barrier)**：结合 `ArtifactAcceptanceCriteria` 验收规则，物理校验交付物（目标文件是否存在、文件字节是否大于零、关键分析结论是否存在）。即便进程 exit 0，若交付物完全为空，立即判定为“静默失败”并自动生成阻断性待办事故单。

## 2. 核心架构设计
- `cronIncidentTypes.ts`: 纯粹强类型系统，零 `any`，定义事故实体、验收规则、任务执行运行记录及度量指标；
- `silentFailureBarrierEngine.ts`: 纯函数业务逻辑引擎，执行交付物物理验收断言与智能事故分类（识别 429、401、Timeout、以及 Exit 0 假成功）；
- `useCronIncidentStore.ts`: 基于 Zustand 的响应式状态机，负责事故清单管理、筛选过滤、未签收待办流转、单条/批量 Ack 签收、重试触发与新运行结果物理断言注入；
- `CronIncidentAlertBadge.tsx`: 顶部轻量级警示徽章，在存在假成功静默失败时提供高危呼吸动画警示并一键直达抽屉；
- `CronIncidentDrawer.tsx`: 全功能事故诊断与待办抽屉，展示物理断言失败证据、Exit 0 假成功高亮、支持单条/批量 Ack、重试与历史诊断深链；
- `CronIncidentCenterContainer.tsx`: 模块顶层自适应聚合容器。

## 3. 工程质量与安全红线守则
- **零 any 约束**：全量代码均使用严格强类型约束；
- **单文件行数受控**：各文件行数均严格保持在 350 行以内（远低于 400 行红线）；
- **零原生 emoji**：全部采用统一的 Lucide 矢量图标；
- **全括号与代码健壮性**：所有 `if` 均显式包裹 `{}`；
- **无障碍访问 a11y**：严格使用语义化 `<dialog>`、`<output>`、`<section>` 及关联 `<label>`。
