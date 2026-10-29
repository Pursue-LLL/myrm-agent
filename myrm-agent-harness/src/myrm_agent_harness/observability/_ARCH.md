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
## Key Dependencies

- `toolkits` (via diagnostics probes)
