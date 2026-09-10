---
name: pure-domain-headless-agent
description: "Configure ultra-secure, specialized Headless Agents by completely disabling generic builtin tools (no bash, no unvetted file tools) and exposing deterministic Agent-as-a-Function execution boundaries."
version: "1.0.0"
category: "engineering"
tags:
  - headless-agent
  - no-builtin-tools
  - domain-action-space
  - agent-as-a-function
  - anti-dilution
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# Pure Domain No-Builtin Tools & Headless Agent-as-a-Function (纯领域无通用工具动作空间与函数化智能体技能)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

A dedicated systems engineering skill for building hyper-focused, risk-free **Domain-Specific Headless Agents**.

In traditional agent systems, general-purpose tools (`bash_code_execute_tool`, `file_edit_tool`, `web_search_tool`) are blanket-injected into every prompt. For mission-critical enterprise workloads (e.g. KYC verification, financial ledger settlement, medical record redaction), this causes:
1. **Severe Attention Dilution**: The LLM writes clumsy python scripts instead of calling optimized domain micro-tools.
2. **Security Vulnerability**: Broad file and shell access violates zero-trust principles.
3. **Non-Deterministic Orchestration**: Agents ramble and hallucinate instead of functioning as predictable RPC functions.

This skill governs the configuration of **Zero-Builtin Action Spaces** and deterministic **Agent-as-a-Function Interfaces**.

---

## The 4-Pillar Pure Domain Contract (纯领域动作空间四项法则)

```
[Pillar 1: Total Builtin Purge (清空默认通用工具)]
  - Set `no_builtin_tools: true` in Agent Profile YAML
  - Strips all global bash, web, and generic file execution tools from the context window
  - Eliminates 1,500+ tokens of unused tool schema definitions
         ↓
[Pillar 2: Explicit Domain Action Injection (显式挂载领域微工具)]
  - Inject ONLY business-validated micro-tools (e.g. `query_ledger_db`, `verify_tax_id`)
  - Enforce strict typing on every parameter (zero `Any` types)
         ↓
[Pillar 3: Headless Function Contract (函数式单进单出契约)]
  - Input: Well-formed JSON payload (`{"account_id": "...", "transaction_id": "..."}`)
  - Execution: Single-turn or minimal-bounded reasoning loop (max 3 turns)
  - Output: Strict schema-conforming JSON response (`{"status": "APPROVED", "audit_code": "..."}`)
         ↓
[Pillar 4: Zero-Escape Guardrail & Audit Log (沙箱零逃逸与确定性审计)]
  - Absolute ban on outbound internet access unless routed through an audited proxy
  - Output full execution trace with deterministic cryptographic signature
```

---

## Configuration Spec (`agent-profiles/domain-settlement.yaml`)

```yaml
agent_id: "domain-financial-settlement"
name: "Financial Ledger Settlement Agent"
version: "1.0.0"

# Core Architecture: Pure Domain Mode
action_space:
  no_builtin_tools: true              # Completely disables bash, generic file read/write, etc.
  allow_tool_overriding: true         # Permits local micro-tools to override namespace conflicts
  allowed_domain_tools:
    - "ledger_reconciliation_tool"
    - "banking_gateway_query_tool"
    - "compliance_audit_log_tool"

execution_mode: "headless_function"   # Optimized for headless RPC / REST pipeline integration
max_execution_turns: 3                # Bounded deterministic execution ceiling
timeout_seconds: 15

input_schema:
  type: "object"
  required: ["batch_id", "currency", "total_amount"]
  properties:
    batch_id: { type: "string" }
    currency: { type: "string", enum: ["USD", "CNY", "EUR"] }
    total_amount: { type: "number" }

output_schema:
  type: "object"
  required: ["settlement_status", "reconciled_count", "discrepancy_amount"]
  properties:
    settlement_status: { type: "string", enum: ["SUCCESS", "FAILED", "FLAGGED_FOR_HITL"] }
    reconciled_count: { type: "integer" }
    discrepancy_amount: { type: "number" }
```

---

## Operating Invariants
- **No Free-Form Banter**: Headless agents must not emit conversational niceties ("Hello!", "Sure thing, I'm analyzing..."). The response body must be purely parseable JSON.
- **Fail-Fast SLA**: If domain tools are unresponsive or input validation fails, abort immediately with an error payload rather than looping endlessly.
