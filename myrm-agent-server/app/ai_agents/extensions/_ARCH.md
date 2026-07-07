# ai_agents/extensions/

## 架构概述

AgentExtension 具体实现（安全/子 Agent/任务自适应等）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `archive_checkpoint_memory.py` | 模块 | Persist pruned tool-output summaries and emit ledger / SSE notifications. | ✅ |
| `pre_compact_memory.py` | 模块 | Inject semantic memory recall before context compaction and record ledger events. | ✅ |
| `security_policy_extension.py` | 模块 | Extension that configures the agent's security policies and PII handling. | ✅ |
| `subagent_extension.py` | 模块 | Registers subagent delegation tools on ``agent._tool_registry`` in ``on_agent_init`` (before first ``create_agent``). | ✅ |
| `task_adaptive_extension.py` | 模块 | Extension that dynamically injects task-adaptive JIT guidance middleware. | ✅ |
| `zero_cost_memory.py` | 模块 | Extension that intercepts evicted tool calls/responses from the ContextPipeline and publishes `MEMORY_OPERATION` SSE events for frontend toast notifications. | ✅ |
