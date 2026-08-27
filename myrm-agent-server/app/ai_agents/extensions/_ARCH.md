# ai_agents/extensions/

## 架构概述

AgentExtension 具体实现（安全/子 Agent/任务自适应等）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `archive_checkpoint_memory.py` | 模块 | Persist pruned tool-output summaries and emit ledger / SSE notifications. | ✅ |
| `extraction_lifecycle.py` | 模块 | Harness `auto_extract_memories` lifecycle observer → ledger + SSE；支持 `source` / `is_retry` metadata；`source=auto_extract_memories` 且非重试（`is_retry=False`）的提取失败自动入持久化重试队列（防无限循环：手动重试/worker 失败不再次入队） | ✅ |
| `pre_compact_memory.py` | 模块 | Inject semantic memory recall before context compaction and record ledger events. | ✅ |
| `security_policy_extension.py` | 模块 | Extension that configures the agent's security policies and PII handling. | ✅ |
| `subagent_extension.py` | 模块 | Registers subagent delegation tools on ``agent._tool_registry`` in ``on_agent_init`` (before first ``create_agent``). | ✅ |
| `zero_cost_memory.py` | 模块 | Extension that intercepts evicted tool calls/responses from the ContextPipeline, auto-extracts long-term memories in the background, and publishes `MEMORY_OPERATION` SSE events. Deep PII scan is resolved from the live `PrivacyPolicy` at extraction time (pooled-agent reuse safe). Integrated with sandbox write gate to skip tool eviction extraction for sandbox-capable agents. | ✅ |
