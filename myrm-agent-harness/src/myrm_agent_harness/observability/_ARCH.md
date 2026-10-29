# observability/

## Overview
Observability tools for Myrm Agent framework. Provides Prometheus metrics, auth failure detection, active health diagnostics, and request tracing context for log correlation.

**Naming disambiguation** (same word, different packages — do not merge or relocate):

| Path | Responsibility |
|------|----------------|
| **`myrm_agent_harness.observability`** (this package) | Metrics, health probes, ContextVar log tracing |
| `myrm_agent_harness.agent.streaming.broadcast` | Chat tool SSE (`ToolBroadcastBus`) |
| `myrm_agent_harness.infra.pubsub` | Server business SSE (`PubSubBus`) |
| `myrm_agent_harness.infra.tracing` | **OpenTelemetry** distributed tracing (optional `[observability]` extra) |
| `toolkits/*/observability.py` | Per-toolkit business-neutral operation DTOs |

`toolkits/` may depend on this package per [toolkits/_ARCH.md](../toolkits/_ARCH.md) Allowed Dependencies.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Observability tools — auth detection, tracing primitives re-export. | ✅ |
| auth_detector.py | Core | Authentication failure detection for circuit breaker logic. | ✅ |

| Submodule | Description |
|-----------|-------------|
| audit_trail/ | Dual-track audit log, redaction, and compliance dossiers. |
| digest/ | Health evaluation digest. |
| metrics/ | Generic metrics utilities; Prometheus counters require `[observability]` extra (NoOp fallback otherwise). |
| diagnostics/ | Framework-level self-inspection — health probes (incl. gateway runtime vitals), benchmark hook registry, and diagnostic protocol. |
| thought_telemetry/ | 长推理思考链（CoT）流式遥测与失控死循环守护子包：毫秒耗时度量、自纠偏步骤特征识别、N-gram 死循环熔断与软中断纠偏。 |
| timeline_visualizer/ | 任务执行透视镜与技能调用时序可视化核心引擎：毫秒级耗时追踪、时序瀑布流、步骤状态树与插嘴打断。参见 [timeline_visualizer/_ARCH.md](timeline_visualizer/_ARCH.md)。 |
| tracing/ | ContextVar-based request tracing (trace_id / session_id) with logging.Filter and JSON formatter. |
| diagnostics_bundle/ | 端内沙箱现场全景诊断打包与自愈凭证引擎：生命体征抓取、PII/Secret 深度脱敏与防篡改 HMAC 校验和。参见 [diagnostics_bundle/_ARCH.md](diagnostics_bundle/_ARCH.md)。 |
| cron_doctor/ | Cron 自动化任务舰队全景健康体检医生与预防性隐患自查引擎：6 大健康门禁只读扫描（执行/交付/回执/调度逾期/脚本/工作区）、隐患聚合诊断与外科手术式修复指引。参见 [cron_doctor/_ARCH.md](cron_doctor/_ARCH.md)。 |
| delivery_dossier/ | 跨智能体任务交付证据卷宗、资产真实有效性与摩擦浪费可观测性引擎：5大维度不可变交付证据（Spec/指纹/工具/物理凭证/验收）、分层资产效能度量与摩擦刺客资产识别。参见 [delivery_dossier/_ARCH.md](delivery_dossier/_ARCH.md)。 |
| rate_limit_governor/ | 客户端主动限流预测阀门、按模型动态配额自适应调度与零 429 顺滑放行引擎：多厂商响应头侦听、前置微延迟平滑削峰 (200~500ms) 与多并发子任务配额切片隔离。参见 [rate_limit_governor/_ARCH.md](rate_limit_governor/_ARCH.md)。 |
| org_spend_limit/ | 团队共享智能体组织月度限额、逐 Query 标签归因与超限熔断套件：群聊/私信分级记账、80% 软预警与 100% 硬限额熔断、按身份/Surface 审计归因。参见 [org_spend_limit/_ARCH.md](org_spend_limit/_ARCH.md)。 |
| diagnostic_stream/ | run-stream 协议诊断事件分离与正常消息流解耦套件：双轨物理隔离正轨用户消息与旁路诊断告警，提供 ACP 会话 Hook 与多维分类统计。参见 [diagnostic_stream/_ARCH.md](diagnostic_stream/_ARCH.md)。 |
| rate_limit_split/ | 限流来源拆分与失败归因套件：429 按自身限流 (myrm) 与上游拒绝 (upstream) 拆分，失败按模型厂商 (provider) 打标，未打标总数严格保持不变。参见 [rate_limit_split/_ARCH.md](rate_limit_split/_ARCH.md)。 |
| enterprise_credit_cockpit/ | 企业用量与风险运营驾驶舱引擎：统一企业 Credit 池跨端治理、人-时-数-险同链路审计留痕与穿透式治理大盘。参见 [enterprise_credit_cockpit/_ARCH.md](enterprise_credit_cockpit/_ARCH.md)。 |
| evidence_cross_verification/ | 多源证据交叉验证与四分制置信度根因排查套件：静态代码、分布式 Trace、运行时日志与知识库历史四维立体现证，四分制置信度推导与行动派修复补丁交付。参见 [evidence_cross_verification/_ARCH.md](evidence_cross_verification/_ARCH.md)。 |
| sandbox_hardware_telemetry/ | 多维度沙箱硬件资源动态遥测与三级阶梯式失控死循环自动熔断器套件：CPU/RAM/Disk/Network 秒级度量采样、三级阶梯自愈拦截 (80% 预警 ➔ 90% 挂起 ➔ 95% 硬熔断) 与现场事故历史。参见 [sandbox_hardware_telemetry/_ARCH.md](sandbox_hardware_telemetry/_ARCH.md)。 |
## Key Dependencies

- `toolkits` (via diagnostics probes)
