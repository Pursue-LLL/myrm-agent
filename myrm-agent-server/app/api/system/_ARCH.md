# api/system/

## 架构概述

系统信息、版本、存储优化与受控关机 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | System API routes. | ✅ |
| `router.py` | 路由 | Ingress 需求/URL、LAN 网络信息、存储磁盘信息与会话数据库智能优化（预检/FTS optimize/VACUUM/WAL truncate）、按类别的存储占用台账（`/storage/governance`，只读，类别名由前端本地化）、支持排障包、恢复点（`/storage/snapshots*`，恢复需重启后生效）、OpenTelemetry 遥测态势探针 (`GET /telemetry-posture` 支持 active/degraded_console 运行时强类型暴露) | ✅ |
| `sandbox_recreate.py` | 路由 | 沙箱「重置环境」(`POST /sandbox/recreate`，仅 SaaS 沙箱模式；由 `router.py` 挂载)：代请求控制平面换新容器（持久卷上的工作区文件、聊天、记忆、设置保留）；请求体 `reset_python_env=true`（默认关闭，备份恢复后的「立即重启」不带）时额外在下次启动清除智能体安装的 Python 包：调用控制平面前写重置标记，除控制平面返回 202 外的任何结局（拒绝、不可达、请求被取消而结果未知）都撤回本次请求自己写下的标记（换容器期间旧容器仍在服务，重复点击被控制平面以「正在重建」拒绝时，不会撤掉首次点击留下的标记），由 `services/infra/python_env_reset` 在新容器启动时消费；控制平面只给旧容器 10 秒停止窗口，因此存在运行中的后台 shell 任务或任一 Agent 运行（对话轮次 / cron / IM 渠道 / 看板 / 评测 / 子 Agent，读 `AgentGateway` 与 `run_activity`）时直接 409 拒绝，不发起控制平面请求 | ✅ |
| `schemas.py` | 数据结构 | System API 请求、响应与存储治理数据传输模型 (Pydantic) | ✅ |
| `port_inspector.py` | 路由 | 端口占用一键排查 (`GET /ports/{port}/inspect`)、父子进程树溯源 (`GET /processes/{pid}/lineage`) 与安全终止进程 (`POST /processes/{pid}/kill`)，内置关键系统进程与自身守护保护防火墙 | ✅ |
| `multi_tier_health_api.py` | 路由 | 分层健康检查 (`GET /health/multi-tier`) 与单次任务因果 TraceSpan 树全景查询 (`GET /traces/{trace_id}`) | ✅ |
| `failure_triage_api.py` | 路由 | Agent 四大经典失效表象六断点自动分诊 (`POST /failure-triage`) 与就地重新投递自愈 (`POST /failure-triage/redispatch`) | ✅ |
| `retrieval_trace_api.py` | 路由 | 上下文检索决策树查询 (`GET /retrieval-traces/{trace_id}`) 与 OpenViking 风格分层下钻剪枝实验场模拟 (`POST /retrieval-traces/simulate`) | ✅ |
| `resource_ledger_api.py` | 路由 | 物理硬件占用与认知 Token 双轨混合全景对账单 (`GET /resource-ledger/{task_id}`) 与 AFP 算力预估及预算防超支熔断 (`POST /resource-ledger/estimate`) | ✅ |
| `labor_acceleration_api.py` | 路由 | 白领劳务效能加速度量化 (`GET /labor-acceleration/{task_id}`)、即时计算 (`POST /labor-acceleration/calculate`) 与月度生产力投资回报透视看板 (`GET /labor-acceleration/monthly-summary`) | ✅ |
| `issue_ticketing_api.py` | 路由 | 端内沙箱现场全景诊断打包加密提交与闪电工单分发 (`POST /tickets/submit`)、工单实时进度与 SLA 追踪 (`GET /tickets/{ticket_id}`) 以及保全持久 Volume 原地一键热重启自愈 (`POST /sandbox/{sandbox_id}/self-heal-reboot`) | ✅ |
| `workflow_burn_api.py` | 路由 | 海量并发 Agent 编排流水线实时 Token 燃速全景 HUD 查询 (`GET /workflow-burn/{workflow_id}`)、执行检查点平滑上报 (`POST /workflow-burn/record-checkpoint`) 与阶梯预算动态调整恢复 (`POST /workflow-burn/{workflow_id}/adjust-budget`) | ✅ |
| `coordination_friction_api.py` | 路由 | 人机协调摩擦度与监督衰减全景记分板 (`GET /coordination-friction/scoreboard`)、人工介入与打回重做事件上报 (`POST /coordination-friction/record-intervention`) 以及模板监督衰减曲线查询 (`GET /coordination-friction/decay-curve/{template_type}`) | ✅ |
| `cron_doctor_api.py` | 路由 | Cron 自动化任务舰队全景健康体检巡检 (`POST /cron/doctor`，扫描执行/交付/回执/逾期/脚本/工作区六大门禁) 与外科手术式一键修复 (`POST /cron/{job_id}/quick-fix`) | ✅ |
| `delivery_budget_api.py` | 路由 | 多智能体整轮交付全生命周期成本核算、未知用量审计账本 (`GET /delivery-budget/{delivery_id}`)、尝试记录上报 (`POST /delivery-budget/record-trial`) 与硬预算熔断调整 (`POST /delivery-budget/{delivery_id}/adjust-budget`) | ✅ |
| `agentic_traffic_api.py` | 路由 | AI Agent 流量精准解构、跳出归因与静默审判大盘 (`GET /agentic-traffic/analytics`)、访问记录上报 (`POST /agentic-traffic/record-visit`) 与 AEO 页面诊断 (`POST /agentic-traffic/diagnose-page`) | ✅ |
| `debug_share_api.py` | 路由 | 一键安全脱敏诊断包生成 (`POST /debug-share/dump`)、加密阅后即焚分享短链 (`POST /debug-share/ephemeral-link`) 与自毁消费读取 (`GET /debug-share/view/{share_token}`) | ✅ |
| `token_economics_api.py` | 路由 | 长任务 Token 经济学透明透视 (`POST /token-economics/evaluate`)、单位成本基线漂移归因 (`POST /token-economics/drift-audit`) 与算力防刺客熔断刹车 (`POST /token-economics/guard-check`) | ✅ |
| `delivery_dossier_api.py` | 路由 | 跨智能体交付证据卷宗归档 (`POST /delivery-dossier/archive`)、根据 ID/Task 检索卷宗 (`GET /delivery-dossier/{id}`) 与分层资产摩擦指数度量 (`GET /delivery-dossier/asset-friction/all`) | ✅ |
| `rate_limit_governor_api.py` | 路由 | 客户端主动流量整形门禁预检 (`POST /rate-limit-governor/pre-check`)、上游限流头嗅探 (`POST /rate-limit-governor/update-headers`)、实时遥测大盘 (`GET /rate-limit-governor/status`) 与工作区子 Agent 配额切片隔离治理 (`/rate-limit-governor/slices*`) | ✅ |
| `context_savings_api.py` | 路由 | 上下文拦截节流指标登记 (`POST /context-savings/record-tool`)、会话战报查询 (`GET /context-savings/session/{session_id}`)、7 维工程障碍模式扫描 (`POST /context-savings/analyze-session`) 与多角色效能大盘 (`GET /context-savings/engineering-insights`) | ✅ |
| `reasoning_semantics_api.py` | 路由 | 按提供方口径归一化 Token 统计 (`POST /reasoning-semantics/normalize`)、不变量契约校验与自愈 (`POST /reasoning-semantics/verify-invariant`) 以及已知厂商口径策略表 (`GET /reasoning-semantics/policies`) | ✅ |
| `org_spend_limit_api.py` | 路由 | 组织级月度 Agent 共享预算限额配置 (`POST /org-spend-limit/configure`)、群聊公摊 vs 私聊自费分级治理预检 (`POST /org-spend-limit/pre-check`)、算力流水上报 (`POST /org-spend-limit/record-spend`)、总览水位对账 (`GET /org-spend-limit/summary/{org_id}`) 与 ident 身份标签归因排行 (`GET /org-spend-limit/attributions/{org_id}`) | ✅ |
| `knowledge_compounding_api.py` | 路由 | 知识复利五大闭环指标全景记分板 (`GET /knowledge-compounding/scoreboard`) 与即时进化体检及劣化告警扫描 (`POST /knowledge-compounding/evaluate`) | ✅ |
| `turn_context_provenance_api.py` | 路由 | 会话逐轮上下文装配来源清单上报 (`POST /turn-context/manifest/record`)、单轮凭证指纹查询 (`GET /turn-context/manifest/{session_id}/{turn_id}`)、跨轮最小差异分析 (`POST /turn-context/diff`) 与来源分类 Token 分解 (`GET /turn-context/token-breakdown/{session_id}/{turn_id}`) | ✅ |
| `deployment_funnel_api.py` | 路由 | 部署漏斗流失事件上报 (`POST /deployment-funnel/event`)、用户情绪反馈登记 (`POST /deployment-funnel/feedback`)、漏斗全景转化快照与 Nudge 告警查询 (`GET /deployment-funnel/snapshot/{deployment_id}`) 以及高阶自愈目标一键派发 (`POST /deployment-funnel/dispatch-goal`) | ✅ |
| `stream_metrics_api.py` | 路由 | 流式调用按最终结果计量 (`POST /stream-metrics/session/start`, `/chunk`, `/finalize`) 与无污染聚合大盘查询 (`GET /stream-metrics/aggregate`, `/session/{call_id}`) | ✅ |
| `otel_degrade_api.py` | 路由 | OpenTelemetry 缺失时优雅降级姿态查询 (`GET /otel-degrade/status`)、主动探测 (`POST /otel-degrade/probe`) 与依赖缺失模拟 (`POST /otel-degrade/simulate`) | ✅ |
| `diagnostic_stream_api.py` | 路由 | run-stream 协议诊断事件双轨解耦派发 (`POST /diagnostic-stream/emit`)、历史事件查询 (`GET /diagnostic-stream/events`) 与多维分布统计 (`GET /diagnostic-stream/stats`) | ✅ |
| `turn_usage_api.py` | 路由 | 回合级 Billed Usage 双计数 API (`POST /turn-usage/record-round`)、双计数账单与缓存决策对比 (`GET /turn-usage/summary/{session_id}/{turn_id}`) 与自适应形状回写 (`POST /turn-usage/rewrite-shape`) | ✅ |
| `context_breakdown_api.py` | 路由 | 上下文用量七分类占比解析 (`POST /context-breakdown/resolve`) 与 60%/90% 警戒线标准配置 (`GET /context-breakdown/thresholds`) | ✅ |
| `local_sink_api.py` | 路由 | 本地盘可观测性落盘兜底配置 (`POST /local-sink/config`)、状态监控 (`GET /local-sink/status`)、Spans 链路查询 (`GET /local-sink/spans`) 与记录 (`POST /local-sink/record-span`) | ✅ |
| `rate_limit_split_api.py` | 路由 | 429 限流来源拆分与失败归因指标 (`GET /rate-limit-split/metrics`)、限流事件上报 (`POST /rate-limit-split/record-rate-limit`)、厂商失败上报 (`POST /rate-limit-split/record-failure`) 与计数器重置 (`POST /rate-limit-split/reset`) | ✅ |
| `enterprise_credit_cockpit_api.py` | 路由 | 企业级统一 Credit 池配额与风险运营驾驶舱 (`GET /enterprise-credit/cockpit`)、人-时-数-险同链路审计上报 (`POST /enterprise-credit/record`)、配额重设 (`POST /enterprise-credit/configure-quota`) 与穿透检索 (`GET /enterprise-credit/audit-trail`) | ✅ |
| `unattended_reliability_api.py` | 路由 | 无人值守可靠性三联自证大盘 (`GET /unattended-reliability/score`)、运行审计上报 (`POST /unattended-reliability/record`)、一键验收基准复跑 (`POST /unattended-reliability/run-benchmark`) 与计数重置 (`POST /unattended-reliability/reset`) | ✅ |
| `custom_agent_insights_api.py` | 路由 | 自定义智能体洞察与运营观测大盘 (`GET /custom-agent-insights/insights`)、交互意图归类上报 (`POST /custom-agent-insights/record-interaction`)、技能漏斗健康记录 (`POST /custom-agent-insights/record-skill`)、人机卡点与 ROI 登记 (`POST /custom-agent-insights/record-hitl`) 与重置 (`POST /custom-agent-insights/reset`) | ✅ |
| `evidence_cross_verification_api.py` | 路由 | 多源证据交叉验证与四分制置信度根因排查大盘 (`POST /evidence-verification/diagnose`)、单条事实证据上报 (`POST /evidence-verification/record-evidence`)、历史诊断查询 (`GET /evidence-verification/recent-diagnoses`) 与重置 (`POST /evidence-verification/reset`) | ✅ |
| `composite_usage_ledger_api.py` | 路由 | 六维复合主键任务级持久化分摊账本与双轨对账大盘 (`POST /composite-usage-ledger/record`)、发票回填对账 (`POST /composite-usage-ledger/reconcile`)、明细查询 (`GET /composite-usage-ledger/records`)、聚合宏观看板 (`GET /composite-usage-ledger/summary`) 与重置 (`POST /composite-usage-ledger/reset`) | ✅ |
| `ambient_auxiliary_accounting_api.py` | 路由 | 环境感知式用量记账与任务维度精准归因 API (`POST /ambient-auxiliary/record`)、双轨用量大盘查询 (`GET /ambient-auxiliary/report`)、快照流查询 (`GET /ambient-auxiliary/recent-snapshots`) 与重置 (`POST /ambient-auxiliary/reset`) | ✅ |
| `multimodal_trace_api.py` | 路由 | 多模态 Trace 媒体对象引用解耦与原位三步排查 API (`POST /multimodal-trace/register-media`)、可见性状态更新 (`POST /multimodal-trace/update-visibility`)、调用链记录 (`POST /multimodal-trace/record-trace`)、黄金评测样本加星锁 (`POST /multimodal-trace/pin/{trace_id}`) 与查询 (`GET /multimodal-trace/traces`, `/trace/{trace_id}`) | ✅ |
| `sandbox_hardware_telemetry_api.py` | 路由 | 沙箱硬件资源动态遥测与三级阶梯熔断 API (`POST /sandbox-hardware/sample`)、全景快照查询 (`GET /sandbox-hardware/snapshot`)、阈值动态微调 (`POST /sandbox-hardware/configure`) 与复位重置 (`POST /sandbox-hardware/reset`) | ✅ |
| `event_causality_lineage_api.py` | 路由 | 事件驱动因果溯源与动作归因图谱 API (`POST /event-causality/record`)、单链 DAG 查询 (`GET /event-causality/lineage/{causality_trace_id}`)、多源因果链列表 (`GET /event-causality/lineages`)、修改产物秒级倒排反向归因 (`GET /event-causality/reverse-lookup`) 与重置 (`POST /event-causality/reset`) | ✅ |
| `visual_flight_recorder_api.py` | 路由 | 视觉故障黑匣子录制与切片回放 API (`POST /visual-flight-recorder/push-frame`)、故障切片截断生成 (`POST /visual-flight-recorder/capture-slice`)、切片全景查询 (`GET /visual-flight-recorder/slice/{slice_id}`)、切片列表 (`GET /visual-flight-recorder/slices`)、卡顿状态巡检 (`GET /visual-flight-recorder/stuck-status`) 与复位重置 (`POST /visual-flight-recorder/reset`) | ✅ |
| `dual_domain_metering_api.py` | 路由 | 双域透明计量边界界定与穿透成本核算 API (`POST /dual-domain-metering/record`)、会话双域及三维成本聚合看板 (`GET /dual-domain-metering/summary/{session_id}`)、SHA-256 财务合规对账凭据生成 (`POST /dual-domain-metering/statement/{session_id}`)、对账单列表 (`GET /dual-domain-metering/statements`) 与复位重置 (`POST /dual-domain-metering/reset`) | ✅ |
| `cross_period_milestone_api.py` | 路由 | 多智能体跨周期透视报表与游戏化进阶里程碑 API (`GET /cross-period-milestone/pivot-report`)、活动事件上报驱动经验值 (`POST /cross-period-milestone/activity`)、用户等级与每日任务查询 (`GET /cross-period-milestone/gamification/{user_id}`)、每日任务认领打卡 (`POST /cross-period-milestone/claim-task`)、团队用量与活跃排行榜 (`GET /cross-period-milestone/team-rankings`) 与测试复位 (`POST /cross-period-milestone/reset`) | ✅ |
| `metric_cardinality_api.py` | 路由 | 热点路径指标基数封顶与溢出桶治理 API (`POST /metric-cardinality/sample`)、指标基数与溢出统计 (`GET /metric-cardinality/stats`)、动态上限微调 (`POST /metric-cardinality/configure`) 与测试复位 (`POST /metric-cardinality/reset`) | ✅ |
| `code_freshness_api.py` | 路由 | 运行时代码新鲜度三态判定 API (`GET /code-freshness/report`)、单模块精确新鲜度判定 (`POST /code-freshness/inspect-module`)、监控模块注册 (`POST /code-freshness/register`) 与测试复位 (`POST /code-freshness/reset`) | ✅ |
| `runtime_zombie_reaper_api.py` | 路由 | 运行时进程因果拓扑快照 (`GET /runtime-zombie-reaper/snapshot`)、节点注册 (`POST /runtime-zombie-reaper/register-node`)、父孤儿级联收割强杀 (`POST /runtime-zombie-reaper/reap-orphans`)、死锁轮询熔断探测 (`GET /runtime-zombie-reaper/check-deadlock`)、失败任务归档 (`POST /runtime-zombie-reaper/record-failed-task`) 与复位 (`POST /runtime-zombie-reaper/reset`) | ✅ |
| `delegation_billing_api.py` | 路由 | 外部委托用量透明化与计费分轨 API (`POST /delegation-billing/record`)、跨渠道聚合看板与节省额度汇总 (`GET /delegation-billing/summary`)、明细审计流水 (`GET /delegation-billing/records`) 与复位 (`POST /delegation-billing/reset`) | ✅ |
| `audit_theater_api.py` | 路由 | 用户面审计剧场与数据访问台账 API (`POST /audit-theater/record-access`)、时间线事件上报 (`POST /audit-theater/record-event`)、会话级不可篡改账本 (`GET /audit-theater/ledger/{session_id}`) 与复位 (`POST /audit-theater/reset`) | ✅ |
| `memory_backend_metrics_api.py` | 路由 | 记忆多后端与召回细分阶段维度标签 API (`POST /memory-backend-metrics/sample`)、分后端分阶段 P50/P95 延迟对比报告 (`GET /memory-backend-metrics/report`)、高基数标签 Opt-in 动态开关 (`POST /memory-backend-metrics/configure`) 与复位 (`POST /memory-backend-metrics/reset`) | ✅ |
| `aborted_usage_ledger_api.py` | 路由 | 中止辅助模型调用账本 API (`POST /aborted-usage-ledger/record`)、隔离已知消耗与未知风险聚合大盘 (`GET /aborted-usage-ledger/summary`)、流水查询 (`GET /aborted-usage-ledger/records`) 与复位 (`POST /aborted-usage-ledger/reset`) | ✅ |
| `active_skill_telemetry_api.py` | 路由 | 活跃技能 Span 遥测透传 API (`POST /active-skill-telemetry/record-span`)、按技能聚合 P95 延迟与错误率报告 (`GET /active-skill-telemetry/report`)、Spans 链路查询 (`GET /active-skill-telemetry/spans`) 与复位 (`POST /active-skill-telemetry/reset`) | ✅ |
| `durable_budget_ledger_api.py` | 路由 | 持久化每日预算账本 API (`POST /durable-budget-ledger/record-spend`)、重启无损用量恢复 (`GET /durable-budget-ledger/today-spent`)、丢弃分支差额审计 (`GET /durable-budget-ledger/recovery-summary`)、会话实际账单 (`GET /durable-budget-ledger/session-billed/{session_id}`) 与复位 (`POST /durable-budget-ledger/reset`) | ✅ |
| `unattended_coverage_api.py` | 路由 | 无人值守与多渠道运行事件日志覆盖状态与健康检查 API (`GET /event-log-coverage/summary`)、会话标识校验与按日分片合规性 (`POST /event-log-coverage/validate`) | ✅ |
| `roi_analytics_api.py` | 路由 | 智能体可量化 ROI 生产力大盘与已节省时间价值看板 (`GET /system/roi/dashboard`)、高收益开箱即用工作流列表 (`GET /system/roi/routines`) 与单次负载即时折算 (`POST /system/roi/calculate`) | ✅ |
| `model_ping_api.py` | 路由 | 模型配置一键测速与连通性自检 (`POST /system/model-ping`)，返回首字延迟 TTFT、吞吐量 TPS 与鉴权可用性徽标 | ✅ |
| `shutdown.py` | 模块 | HTTP shutdown/drain control — `POST /shutdown` (graceful SIGTERM), `POST /drain` (begin draining), `DELETE /drain` (cancel drain). | ✅ |



