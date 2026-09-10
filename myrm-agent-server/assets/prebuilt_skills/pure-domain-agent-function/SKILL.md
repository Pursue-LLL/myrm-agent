---
name: pure-domain-agent-function
description: "Pure domain action space restriction, builtin tool overrides, and headless Agent-as-a-Function (AaaF) deterministic single-turn execution contract."
version: "1.0.0"
category: "architecture"
tags:
  - headless-agent
  - agent-as-a-function
  - pure-domain
  - tool-overriding
  - action-space-isolation
  - aaaf
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# Pure Domain Action Space & Headless Agent-as-a-Function (纯净领域动作空间与无头函数化智能体)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

Based on architecture principles from *Pi v0.84.4* ("What happens when all builtin tools are turned off"), this skill defines the contract for running **Pure Domain Agents** and executing **Headless Agent-as-a-Function (AaaF)**.

In mission-critical enterprise domains (SQL generation, financial underwriting, medical guidelines, legal auditing), mounting general-purpose OS tools (`bash_*`, `file_*`, `web_fetch`) dilutes model attention, triggers unnecessary environmental exploration, and introduces security attack surfaces.

---

## 1. Pure Domain Mode Specification (`no_builtin_tools`)

When an Agent Profile or execution parameters declare `no_builtin_tools: true`:

```yaml
agent_profile:
  id: "sql_financial_auditor"
  no_builtin_tools: true  # 彻底关闭 Layer 1 (CORE) 与 Layer 2 (HIGH_PRIORITY) 内置基础工具
  
  # 显式声明仅允许的领域业务工具
  domain_tools:
    - name: "execute_readonly_sql_tool"
      source: "custom_extension"
    - name: "fetch_schema_definition_tool"
      source: "custom_extension"

  # 支持同名工具覆盖 (Clean Overriding)
  # 若领域工具名为 file_read_tool，其以 USER 优先级最高权重直接覆盖框架版本
  override_tools:
    - name: "file_read_tool"
      implementation: "app.custom.audited_file_reader"
```

### Action Space Assembly Gate
1. `ToolRegistry` inspects the `no_builtin_tools` flag.
2. If `True`, skip the automatic injection of `_CORE_TOOLS` (`bash_code_execute_tool`, `file_edit_tool`, `web_fetch_tool`, etc.).
3. The model's Turn 1 prompt binds **only** the explicit domain tools, reducing the action space token overhead by up to 75% and eliminating OS-level hallucination.

---

## 2. Headless Agent-as-a-Function (AaaF) Protocol

Invoke an Agent as an asynchronous, deterministic, typed Python function without launching WebSocket SSE buses or multi-turn chat sessions:

```python
from myrm_agent_harness.agent import run_agent_as_function
from pydantic import BaseModel

class SQLAuditInput(BaseModel):
    query: str
    target_cluster: str

class SQLAuditResult(BaseModel):
    is_safe: bool
    risk_level: str
    identified_issues: list[str]
    optimized_sql: str

# 一键以纯函数方式调用
result: SQLAuditResult = await run_agent_as_function(
    agent_id="sql_financial_auditor",
    input_payload=SQLAuditInput(query="SELECT * FROM transactions", target_cluster="prod_olap"),
    response_model=SQLAuditResult,
    timeout_seconds=15,
)
```

### AaaF Execution Guarantees
- **Zero Chat Session Overhead**: No DB conversation records or message thread instantiation.
- **Deterministic Single/Multi-Step Convergence**: Halts immediately upon returning the structured payload.
- **Strict Exception Propagation**: Tool failures or permission denials raise typed Python exceptions directly to the caller.
