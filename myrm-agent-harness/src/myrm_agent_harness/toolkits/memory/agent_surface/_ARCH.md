# agent_surface/

## Overview

Agent-visible memory I/O layer: LangChain tools, MCP adapter, recall sanitize SSOT,
citations bridge, corpus policy, and wiki/memory write boundary.

Parent index: [../_ARCH.md](../_ARCH.md). System design: [../MEMORY_SYSTEM.md](../MEMORY_SYSTEM.md).

## File Index

| File | Role | Description | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | Package | Agent-facing memory I/O package marker. | — |
| `memory_agent_tools/` | Package | Agent tools: memory_search/save/manage (factory, one module per tool, shared category mapping). | ✅ |
| `_memory_agent_tool_descriptions.py` | Core | LLM-visible tool description facade: save/manage builders (write target, wiki boundary, approval), locale choice, agent/MCP tool-name mapping, and the argument-level scope note for `importance` (`MEMORY_SAVE_IMPORTANCE_FIELD_DESCRIPTION`) that both save surfaces attach to the argument itself. | ✅ |
| `_memory_search_description.py` | Core | memory_search_tool description derived from the corpus policy (EN/ZH): the corpus guide lists exactly the corpora the schema offers, and the sessions routing triggers live only here. | ✅ |
| `_memory_tool_texts_en.py` | Core | English static texts: the memory_save_tool core, its write-target block (offered only under a shared-write policy) and the memory_manage_tool description. | ✅ |
| `_memory_tool_texts_zh.py` | Core | Chinese static texts, semantically aligned with the English ones. | ✅ |
| `memory_manage_core.py` | Core | Update / delete / correct / rate addressed by memory id alone: the stored memory's type picks the store and the applicable actions; one implementation for the agent tool and the MCP adapter. Only an explicit pin or lock refuses the agent's delete, rewrite and correction (`_agent_may_modify` decides the last two); the exact-fact stamp is the classifier's, not the user's decision. An update reply says so when the importance it was given did not reach the stored memory (a rule stores none), so the model cannot tell the user the importance changed. A correction of a rule is answered with a pointer to `update`: deleting the rule and saving it again would leave the old rule gone while the new one waits for approval. | ✅ |
| `memory_search_policy.py` | Core | Corpus ACL, write bounds, optional wiki/sessions backends, and the one source of which corpora a policy enables (`enabled_search_corpora`) and offers (`advertised_search_corpora`). | ✅ |
| `memory_search_execution.py` | Core | memory/wiki/sessions search execution with domain-scoped pruning and heuristic fallback, plus the by-id single-memory drill-down (`drill_down_single_memory` fetches the memory and hands it to `format_drill_down_output`); the memory and sessions searches take `since`/`until` as instants that the tool entry parsed once, so both read one window; a memory search that finds nothing gets the shared zero-hit reply (`memory_recall_no_result.py`), and a sessions search hands its explicit `since`/`until` to the formatter so an empty result names the window (an expand request ignores the window and passes none), and the requester's zone so its hit times are written in it. | ✅ |
| `memory_recall_formatting.py` | Core | Recall sanitize SSOT, save ack, source_error suffix, the by-id memory read-back output (`format_drill_down_output`: overview or full text, sanitized, with the untrusted preamble), and the `since`/`until` bound parser (`parse_time_bound`: ISO 8601, or an amount counted back from now in `m` minutes, `h`, `d`, `w`, `y`; there is no month unit, a month is `30d`; a date or time without an offset is read in the `zone` the caller passes, UTC without one, and a date without a time names its whole day in that zone, so as `until` it ends at the close of that day, taking the later of two instants when the clocks turn back at midnight). | ✅ |
| `memory_recall_budget.py` | Core | Recall output budget guardrails. | ✅ |
| `memory_recall_no_result.py` | Core | The reply to a memory search that finds nothing, shared by `memory_search_tool` and the MCP `memory_recall`: whenever rules were in scope it says how stored rules are matched (one exact phrase, not by meaning) and how to list them, so a model does not conclude a rule is missing and save a duplicate; when an explicit `since`/`until` window applied to a searched type that reads it (knowledge, event, conversation) it names that save-time window and says to retry without it, so a model does not conclude that a memory saved outside the window does not exist. `describe_time_window` renders the bounds (UTC, to the minute) and is the same renderer the sessions-corpus reply uses, so one instant reads the same on every surface. | ✅ |
| `memory_citations.py` | Core | cited_memory_ids SSE bridge (sources via tool metadata → SourceTracker). | ✅ |
| `tool_result_sources.py` | Core | Pack/unpack metadata.sources for memory_search wiki/sessions results. | ✅ |
| `mcp_server/` | Package | MCP adapter (recall/list/store/manage), one module per tool plus per-request context. | ✅ |
| `wiki_memory_boundary.py` | Core | Wiki vs memory write boundary heuristics. | ✅ |
| `transient_fact_boundary.py` | Core | Transient business state memory write boundary heuristics. | ✅ |
| `write_failure_feedback.py` | Core | Model-facing result for a failed save/manage call: explicit "Not saved" rejection for write-scan rejections, protected-memory refusal text, the message of a `MemoryRejectedError` as written (an out-of-range score, a transient business fact), generic fallback otherwise (shared by tools and MCP). | ✅ |
| `rule_write_boundary.py` | Core | Agent-facing rejection message for writes to user-protected (`is_user_protected`) memories; the guard itself lives in `MemoryManager.update_memory`. | ✅ |

## Key Dependencies

- `../manager.py`, `../types/`, `../conversation_search/`, `../domain_types.py`
- `../session.py`, `../config.py`, `../observability.py`, `../_internal/`, `../protocols/` (type-only: `ConversationSearchProtocol`)
- `core` (security detection and redaction, events, the request-zone accessor `context_vars.request_timezone`), `utils` (locale, progress sink, context formatting), `toolkits/wiki/` (wiki corpus source citations and query result types)
