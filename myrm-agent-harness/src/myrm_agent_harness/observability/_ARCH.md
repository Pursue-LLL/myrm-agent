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
| timeline_visualizer/ | 任务执行透视镜与技能调用时序可视化核心引擎：毫秒级耗时追踪、时序瀑布流、步骤状态树与插嘴打断。参见 [timeline_visualizer/_ARCH.md](timeline_visualizer/_ARCH.md)。 |
| tracing/ | ContextVar-based request tracing (trace_id / session_id) with logging.Filter and JSON formatter. |
| invariants/ | Runtime invariant assertions and registry: cross-event causality, state-machine transition and data-integrity checks, no-op in production and fail-fast in development. See [invariants/_ARCH.md](invariants/_ARCH.md). |
| spend_control/ | Four-tier progressive spend control and soft quota intervention engine (visibility, soft gate, auto-downgrade, approval pause). See [spend_control/_ARCH.md](spend_control/_ARCH.md). |
| storage_governance/ | Read-only attribution of persistent agent state disk usage to declared categories (layout, inspector, snapshots). See [storage_governance/_ARCH.md](storage_governance/_ARCH.md). |
## Key Dependencies

- `toolkits` (via diagnostics probes)
