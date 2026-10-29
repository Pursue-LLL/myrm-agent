# api/system/

## 架构概述

系统信息、版本、存储优化与受控关机 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `router.py` | 路由 | Ingress 需求/URL、LAN 网络信息、存储磁盘信息与会话数据库智能优化（预检/FTS optimize/VACUUM/WAL truncate）、按类别的存储占用台账（`/storage/governance`，只读，类别名由前端本地化）、支持排障包、恢复点（`/storage/snapshots*`，恢复需重启后生效）、OpenTelemetry 导出实测态势（`GET /telemetry-posture`：状态、脱敏端点、协议、采样器、内容外发开关、指标管线 `metrics_status`（`off`/`ready`/`active`/`failing`，按最近一次投递实测）、已导出 Span、失败批次与被隐私守卫拦截的 Span 计数与最近成功/失败时间，全部取自运行中的导出管线，没有写死的能力标志；读取失败时返回 `status=error`；沙箱托管实例（`DEPLOY_MODE=sandbox`）返回 `managed=true` 且不披露采集端地址，因为采集端归平台运营者、用户无需也无法配置） | ✅ |
| `sandbox_recreate.py` | 路由 | 沙箱「重置环境」(`POST /sandbox/recreate`，仅 SaaS 沙箱模式；由 `router.py` 挂载)：代请求控制平面换新容器（持久卷上的工作区文件、聊天、记忆、设置保留）；请求体 `reset_python_env=true`（默认关闭，备份恢复后的「立即重启」不带）时额外在下次启动清除智能体安装的 Python 包：调用控制平面前写重置标记，除控制平面返回 202 外的任何结局（拒绝、不可达、请求被取消而结果未知）都撤回本次请求自己写下的标记（换容器期间旧容器仍在服务，重复点击被控制平面以「正在重建」拒绝时，不会撤掉首次点击留下的标记），由 `services/infra/python_env_reset` 在新容器启动时消费；控制平面只给旧容器 10 秒停止窗口，因此存在运行中的后台 shell 任务或任一 Agent 运行（对话轮次 / cron / IM 渠道 / 看板 / 评测 / 子 Agent，读 `AgentGateway` 与 `run_activity`）时直接 409 拒绝，不发起控制平面请求 | ✅ |
| `schemas.py` | 数据结构 | System API 请求、响应与存储治理数据传输模型 (Pydantic) | ✅ |
| `multi_tier_health_api.py` | 路由 | 分层健康检查 (`GET /health/multi-tier`) 与单次任务因果 TraceSpan 树全景查询 (`GET /traces/{trace_id}`) | ✅ |
| `failure_triage_api.py` | 路由 | Agent 四大经典失效表象六断点自动分诊 (`POST /failure-triage`) 与就地重新投递自愈 (`POST /failure-triage/redispatch`) | ✅ |
| `retrieval_trace_api.py` | 路由 | 上下文检索决策树查询 (`GET /retrieval-traces/{trace_id}`) 与 OpenViking 风格分层下钻剪枝实验场模拟 (`POST /retrieval-traces/simulate`) | ✅ |
| `issue_ticketing_api.py` | 路由 | 端内沙箱现场全景诊断打包加密提交与闪电工单分发 (`POST /tickets/submit`)、工单实时进度与 SLA 追踪 (`GET /tickets/{ticket_id}`) 以及保全持久 Volume 原地一键热重启自愈 (`POST /sandbox/{sandbox_id}/self-heal-reboot`) | ✅ |
| `coordination_friction_api.py` | 路由 | 人机协调摩擦度与监督衰减全景记分板 (`GET /coordination-friction/scoreboard`)、人工介入与打回重做事件上报 (`POST /coordination-friction/record-intervention`) 以及模板监督衰减曲线查询 (`GET /coordination-friction/decay-curve/{template_type}`) | ✅ |
| `cron_doctor_api.py` | 路由 | Cron 自动化任务舰队全景健康体检巡检 (`POST /cron/doctor`，扫描执行/交付/回执/逾期/脚本/工作区六大门禁) 与外科手术式一键修复 (`POST /cron/{job_id}/quick-fix`) | ✅ |
| `debug_share_api.py` | 路由 | 一键安全脱敏诊断包生成 (`POST /debug-share/dump`)、加密阅后即焚分享短链 (`POST /debug-share/ephemeral-link`) 与自毁消费读取 (`GET /debug-share/view/{share_token}`) | ✅ |
| `delivery_dossier_api.py` | 路由 | 跨智能体交付证据卷宗归档 (`POST /delivery-dossier/archive`)、根据 ID/Task 检索卷宗 (`GET /delivery-dossier/{id}`) 与分层资产摩擦指数度量 (`GET /delivery-dossier/asset-friction/all`) | ✅ |
| `rate_limit_governor_api.py` | 路由 | 客户端主动流量整形门禁预检 (`POST /rate-limit-governor/pre-check`)、上游限流头嗅探 (`POST /rate-limit-governor/update-headers`)、实时遥测大盘 (`GET /rate-limit-governor/status`) 与工作区子 Agent 配额切片隔离治理 (`/rate-limit-governor/slices*`) | ✅ |
| `org_spend_limit_api.py` | 路由 | 组织级月度 Agent 共享预算限额配置 (`POST /org-spend-limit/configure`)、群聊公摊 vs 私聊自费分级治理预检 (`POST /org-spend-limit/pre-check`)、算力流水上报 (`POST /org-spend-limit/record-spend`)、总览水位对账 (`GET /org-spend-limit/summary/{org_id}`) 与 ident 身份标签归因排行 (`GET /org-spend-limit/attributions/{org_id}`) | ✅ |
| `knowledge_compounding_api.py` | 路由 | 知识复利五大闭环指标全景记分板 (`GET /knowledge-compounding/scoreboard`) 与即时进化体检及劣化告警扫描 (`POST /knowledge-compounding/evaluate`) | ✅ |
| `turn_context_provenance_api.py` | 路由 | 会话逐轮上下文装配来源清单上报 (`POST /turn-context/manifest/record`)、单轮凭证指纹查询 (`GET /turn-context/manifest/{session_id}/{turn_id}`)、跨轮最小差异分析 (`POST /turn-context/diff`) 与来源分类 Token 分解 (`GET /turn-context/token-breakdown/{session_id}/{turn_id}`) | ✅ |
| `stream_metrics_api.py` | 路由 | 流式调用按最终结果计量 (`POST /stream-metrics/session/start`, `/chunk`, `/finalize`) 与无污染聚合大盘查询 (`GET /stream-metrics/aggregate`, `/session/{call_id}`) | ✅ |
| `diagnostic_stream_api.py` | 路由 | run-stream 协议诊断事件双轨解耦派发 (`POST /diagnostic-stream/emit`)、历史事件查询 (`GET /diagnostic-stream/events`) 与多维分布统计 (`GET /diagnostic-stream/stats`) | ✅ |
| `context_breakdown_api.py` | 路由 | 上下文用量七分类占比解析 (`POST /context-breakdown/resolve`) 与 60%/90% 警戒线标准配置 (`GET /context-breakdown/thresholds`) | ✅ |
| `rate_limit_split_api.py` | 路由 | 429 限流来源拆分与失败归因指标 (`GET /rate-limit-split/metrics`)、限流事件上报 (`POST /rate-limit-split/record-rate-limit`)、厂商失败上报 (`POST /rate-limit-split/record-failure`) 与计数器重置 (`POST /rate-limit-split/reset`) | ✅ |
| `enterprise_credit_cockpit_api.py` | 路由 | 企业级统一 Credit 池配额与风险运营驾驶舱 (`GET /enterprise-credit/cockpit`)、人-时-数-险同链路审计上报 (`POST /enterprise-credit/record`)、配额重设 (`POST /enterprise-credit/configure-quota`) 与穿透检索 (`GET /enterprise-credit/audit-trail`) | ✅ |
| `unattended_reliability_api.py` | 路由 | 无人值守可靠性三联自证大盘 (`GET /unattended-reliability/score`)、运行审计上报 (`POST /unattended-reliability/record`)、一键验收基准复跑 (`POST /unattended-reliability/run-benchmark`) 与计数重置 (`POST /unattended-reliability/reset`) | ✅ |
| `custom_agent_insights_api.py` | 路由 | 自定义智能体洞察与运营观测大盘 (`GET /custom-agent-insights/insights`)、交互意图归类上报 (`POST /custom-agent-insights/record-interaction`)、技能漏斗健康记录 (`POST /custom-agent-insights/record-skill`)、人机卡点与 ROI 登记 (`POST /custom-agent-insights/record-hitl`) 与重置 (`POST /custom-agent-insights/reset`) | ✅ |
| `evidence_cross_verification_api.py` | 路由 | 多源证据交叉验证与四分制置信度根因排查大盘 (`POST /evidence-verification/diagnose`)、单条事实证据上报 (`POST /evidence-verification/record-evidence`)、历史诊断查询 (`GET /evidence-verification/recent-diagnoses`) 与重置 (`POST /evidence-verification/reset`) | ✅ |
| `sandbox_hardware_telemetry_api.py` | 路由 | 沙箱硬件资源动态遥测与三级阶梯熔断 API (`POST /sandbox-hardware/sample`)、全景快照查询 (`GET /sandbox-hardware/snapshot`)、阈值动态微调 (`POST /sandbox-hardware/configure`) 与复位重置 (`POST /sandbox-hardware/reset`) | ✅ |
| `event_causality_lineage_api.py` | 路由 | 事件驱动因果溯源与动作归因图谱 API (`POST /event-causality/record`)、单链 DAG 查询 (`GET /event-causality/lineage/{causality_trace_id}`)、多源因果链列表 (`GET /event-causality/lineages`)、修改产物秒级倒排反向归因 (`GET /event-causality/reverse-lookup`) 与重置 (`POST /event-causality/reset`) | ✅ |
| `unattended_coverage_api.py` | 路由 | 无人值守与多渠道运行事件日志覆盖状态与健康检查 API (`GET /event-log-coverage/summary`)、会话标识校验与按日分片合规性 (`POST /event-log-coverage/validate`) | ✅ |
| `roi_analytics_api.py` | 路由 | 智能体可量化 ROI 生产力大盘与已节省时间价值看板 (`GET /system/roi/dashboard`)、高收益开箱即用工作流列表 (`GET /system/roi/routines`) 与单次负载即时折算 (`POST /system/roi/calculate`) | ✅ |
| `model_ping_api.py` | 路由 | 模型配置一键测速与连通性自检 (`POST /system/model-ping`)，返回首字延迟 TTFT、吞吐量 TPS 与鉴权可用性徽标 | ✅ |
| `shutdown.py` | 模块 | HTTP shutdown/drain control — `POST /shutdown` (graceful SIGTERM), `POST /drain` (begin draining), `DELETE /drain` (cancel drain). | ✅ |



