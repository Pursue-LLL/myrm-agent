---
name: mcp-command-center
description: >-
  Model Context Protocol (MCP) centralized management, pre-call health probes, circuit breaker gating,
  and 30-day token cost auditing. Prevents hung connections, enforces payload size caps,
  and delivers transparent cost analytics across all external tool servers.
version: 1.0.0
category: operations
tags:
  - mcp
  - command-center
  - health-gate
  - cost-audit
  - circuit-breaker
  - token-budget
  - latency-monitoring
  - MCP指挥中心
allowed-tools: file_write_tool file_read_tool bash_code_execute_tool
contract:
  steps:
    - 1. Pre-Call Heartbeat & Probe Gate (Execute lightweight ping/handshake with <= 2000ms latency ceiling)
    - 2. Token Budget & Payload Throttling (Enforce response payload truncation to prevent context blowup)
    - 3. Usage & Latency Ledger Tracking (Log tool invocation events, latency p95/p99, and token consumption)
    - 4. 30-Day Cost & Health Audit Dashboard (Generate structured audit reports with server health grades and recommendations)
  potential_traps:
    - Allowing unmonitored MCP tool calls to hang indefinitely beyond system timeout limits
    - Ingesting unbounded MCP return payloads that exhaust agent context windows
    - Ignoring cascading failures when a downstream MCP server crashes or rate-limits
    - Missing cost attribution when external third-party MCP APIs charge per-request fees
  verification_steps:
    - Confirm pre-call health probe correctly identifies offline or high-latency servers
    - Validate circuit breaker trips after 3 consecutive health probe failures
    - Ensure cost ledger accurately aggregates token volumes and estimated expenditures
  success_criteria:
    - Resilient MCP toolchain with sub-second fail-fast behavior, zero runaway token dumps, and transparent 30-day cost visibility
---

# MCP Command Center: Pre-Call Health Gate & Cost Audit Dashboard (MCP 指挥中心与成本审计)

## Overview

A dedicated skill for platform engineers, LLMOps leads, and multi-agent architects to monitor, govern, and audit
**Model Context Protocol (MCP)** server integrations across local and remote environments.

It eliminates "black-box" MCP failures (infinite hanging, silent disconnects, memory leaks, runaway token consumption)
by introducing proactive pre-call health gating and transparent cost accounting.

---

## The 4-Stage MCP Governance Pipeline (四阶 MCP 治理流水线)

```
Stage 1: Pre-Call Heartbeat & Probe Gate (调用前置健康心跳门禁)
   ├── Issue lightweight ping / ping-handshake (timeout <= 2000ms)
   └── Fast-fail circuit breaker: trip to offline state after 3 consecutive failures
Stage 2: Payload Guardrails & Token Throttling (载荷截断与成本预算拦截)
   ├── Enforce hard output ceiling (default: 8,000 tokens / 32 KB per tool return)
   └── Automatically summarize or summarize-truncate oversized JSON dumps
Stage 3: Event Ledger & Latency Metrics (调用账本与延迟指标追踪)
   ├── Log timestamp, server_id, tool_name, status, latency_ms, input_tokens, output_tokens
   └── Compute rolling p50, p95, p99 latency distributions
Stage 4: 30-Day Cost & Health Audit Dashboard (30天成本与健康度审计看板)
   ├── Aggregate monthly token usage and estimated API cost per server
   └── Output actionable recommendations: decommission dead servers, optimize heavy tools
```

---

## 1. Health Probe Gate & Circuit Breaker State Machine (健康探测门禁与熔断机)

```
       [HEALTHY (绿灯)]
          │ (fail 1, fail 2)
          ▼
       [DEGRADED (黄灯: 警告，限制并发)]
          │ (fail 3)
          ▼
       [TRIPPED / OFFLINE (红灯: 熔断，快速拒绝，触发 fallback)]
          │ (health probe recovery after 30s backoff)
          ▼
       [HALF-OPEN (探测恢复中: 单一试探请求)]
```

- **HEALTHY**: Ping latency <= 1,000ms, success rate >= 99%. Calls proceed normally.
- **DEGRADED**: Ping latency 1,000ms - 3,000ms, or intermittent timeouts. Agent alerts user.
- **TRIPPED**: 3 consecutive probe failures. Agent immediately bypasses or falls back to native micro-tools without waiting 60s.
- **HALF-OPEN**: Allows 1 trial ping after cool-down; restores to HEALTHY upon success.

---

## 2. Token Budget & Payload Throttling (Token 载荷预算门禁)

To protect the host agent from catastrophic context window exhaustion:

| Payload Size | Action Taken | Logging |
|---|---|---|
| **< 4 KB (< 1,000 tokens)** | Direct pass-through | Standard ledger record |
| **4 KB - 32 KB (1,000 - 8,000 tokens)** | Pass-through with Warning tag | Flagged as "High Volume" |
| **> 32 KB (> 8,000 tokens)** | **Mandatory Truncation**: Head 100 lines + Tail 50 lines + Truncation notice | Alert: "Payload Throttled" |

---

## 3. Deliverable Specification: 30-Day Cost & Health Audit Report (`docs/mcp-audit.md`)

```markdown
# MCP Command Center: 30-Day Health & Cost Audit Report

## 1. Server Health Matrix
| Server ID | Transport | Status | Uptime | Avg Latency | p95 Latency | Health Grade |
|---|---|---|---|---|---|---|
| `db-inspector` | stdio | HEALTHY | 99.8% | 120ms | 340ms | A+ |
| `github-tools` | sse | HEALTHY | 98.5% | 450ms | 1,200ms | B |
| `legacy-crm` | stdio | TRIPPED | 42.1% | TIMEOUT | TIMEOUT | F (Decommission) |

## 2. 30-Day Cost & Token Consumption Breakdown
| Server ID | Total Calls | Total Input Tokens | Total Output Tokens | Estimated Cost (USD) | Cost % |
|---|---|---|---|---|---|
| `db-inspector` | 1,420 | 850,000 | 1,200,000 | $4.10 | 18% |
| `github-tools` | 3,890 | 4,200,000 | 6,800,000 | $18.70 | 82% |
| **Total** | **5,310** | **5,050,000** | **8,000,000** | **$22.80** | **100%** |

## 3. High-Leverage Optimization Prescriptions
1. **Throttle `github-tools/list_issues`**: Emitting 45KB per call; enable pagination limit `per_page=10`.
2. **Decommission `legacy-crm`**: Tripped 14 times this week; replace with native REST API tool.
```
