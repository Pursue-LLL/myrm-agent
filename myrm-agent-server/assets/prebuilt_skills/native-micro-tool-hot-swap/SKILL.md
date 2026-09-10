---
name: native-micro-tool-hot-swap
description: >-
  In-process native micro-tool hot-swapping and dual-track plugin harness. Allows
  developers and agents to define lightweight, zero-overhead Python micro-tools
  using the `@agent_tool` decorator, hot-register them into the ToolRegistry across
  cache-aligned ToolLayers (CORE, HIGH_PRIORITY, EXTENDED, EXTERNAL), and dynamically
  swap implementations without subprocess IPC or MCP network overhead.
version: 1.0.0
category: harness-extensibility
tags:
  - micro-tool
  - tool-registry
  - hot-swapping
  - prompt-cache
  - dual-track
  - in-process
  - 进程内微工具
  - 热插拔
  - 工具层级
allowed-tools: file_read_tool file_write_tool file_edit_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Micro-Tool Function Specification — define lightweight Python function with typed TypeHints, docstring, and `@agent_tool` decorator"
    - "Phase 2: ToolLayer & Cache-Key Assignment — map tool to designated ToolLayer (CORE, HIGH_PRIORITY, EXTENDED, EXTERNAL) for prefix-cache stability"
    - "Phase 3: Dynamic In-Process Registration — register tool directly into `ToolRegistry` with zero-IPC overhead"
    - "Phase 4: Hot-Swap & Replay Safety Validation — verify hot-swapping semantics and test invocation with unit assertions"
  potential_traps:
    - description: "Registering dynamic tools into CORE layer, breaking global prompt prefix cache"
      mitigation: "Strict constraint: dynamic micro-tools MUST default to EXTENDED or EXTERNAL layer"
      severity: high
    - description: "Unbounded global state mutation in hot-swapped micro-tools causing race conditions"
      mitigation: "Enforce pure function semantics or explicit context encapsulation"
      severity: high
  verification_steps:
    - step_id: tool_schema_generated
      description: "Ensure LangChain-compatible BaseTool or StructuredTool is synthesized from function signature"
      validation_method: "Verify tool name, description, and args_schema are properly resolved"
      is_required: true
    - step_id: layer_ordering_tested
      description: "Ensure ToolRegistry sort key positions the tool in the designated ToolLayer"
      validation_method: "Verify sort priority conforms to ToolLayer enum ordering"
      is_required: true
  success_criteria: "A verified in-process micro-tool hot-swapped into ToolRegistry with zero network latency and cache-aligned ordering"
  estimated_duration_seconds: 300
---

# In-Process Native Micro-Tool Hot-Swapping & Dual-Track Plugin Harness

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

While external Model Context Protocol (MCP) servers provide process isolation, they introduce **JSON-RPC IPC overhead, network latency, and subprocess lifecycle complexity**. For performance-critical or simple agent primitives (e.g. string formatting, fast regex search, math operations), in-process micro-tools offer 100x lower latency and zero IPC friction.

The `native-micro-tool-hot-swap` skill provides a dual-track plugin architecture: combining heavy external MCP services with high-speed, in-process Python micro-tools organized across prompt-cache-friendly **ToolLayers**.

## Dual-Track Architecture Comparison

```
┌────────────────────────────────────────────────────────┐
│                   Dual-Track Tool Harness              │
├──────────────────────────┬─────────────────────────────┤
│   Track A: Native Micro  │    Track B: External MCP    │
│   (In-Process Python)    │    (Stdio / SSE Subprocess) │
├──────────────────────────┼─────────────────────────────┤
│ • Zero IPC / Subprocess  │ • Full Process Isolation    │
│ • Execution: < 0.1 ms    │ • Execution: 10 - 200 ms    │
│ • `@agent_tool` decorator│ • `mcp.json` server config  │
│ • Cache: ToolLayer sorted│ • Cache: EXTERNAL (Layer 4) │
└──────────────────────────┴─────────────────────────────┘
```

## The 4 ToolLayers for Prompt Cache Optimization

To maximize LLM Prompt Cache hit rates, tools are sorted deterministically into four tiers:

1. **Layer 1: CORE (核心基线层)**:
   100% stable, permanently mounted base tools (`file_read`, `bash`). Never modified dynamically.
2. **Layer 2: HIGH_PRIORITY (高优标配层)**:
   Default-ON tools that can be toggled by user config (`web_search`, `memory_save`).
3. **Layer 3: EXTENDED (扩展能力层)**:
   On-demand, domain-specific in-process micro-tools (`image_transform`, `regex_audit`).
4. **Layer 4: EXTERNAL (外部业务层)**:
   Dynamic MCP tools and third-party API endpoints, placed at the end to isolate cache churn.

## Standard In-Process `@agent_tool` Schema

```python
from myrm_agent_harness.agent.tool_management.tool_layers import ToolLayer

def agent_tool(
    name: str | None = None,
    layer: ToolLayer = ToolLayer.EXTENDED,
    description: str | None = None,
):
    """Decorator to declare an in-process native micro-tool."""
    def decorator(fn):
        fn.__agent_tool__ = True
        fn.__tool_name__ = name or fn.__name__
        fn.__tool_layer__ = layer
        fn.__tool_description__ = description or fn.__doc__
        return fn
    return decorator

# Example Usage:
@agent_tool(name="calc_cagr", layer=ToolLayer.EXTENDED)
def calculate_cagr(start_val: float, end_val: float, years: int) -> float:
    """Calculate Compound Annual Growth Rate between two values."""
    if start_val <= 0 or years <= 0:
        raise ValueError("start_val and years must be positive")
    return (end_val / start_val) ** (1.0 / years) - 1.0
```

## Standard Execution SOP

1. **Define Micro-Tool**: Write typed function with `@agent_tool` and docstrings.
2. **Assign ToolLayer**: Set layer to `EXTENDED` (or `HIGH_PRIORITY` if globally needed).
3. **Hot-Swap into Registry**: Call `registry.register(tool, source=ToolSource.USER)` at runtime.
4. **Assert Cache Position**: Verify `get_tool_registry_sort_key(tool)` maintains prefix stability.
