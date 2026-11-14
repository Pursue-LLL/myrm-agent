# conversation_search/

## Overview
Framework-level conversation recall toolkit. Provides conversation search DTOs and shared formatting helpers; the `ConversationSearchProtocol` contract lives in `protocols/conversation_search.py` and is implemented by the host. Agents reach it only through `memory_search_tool(corpus=sessions)`; there is no standalone LLM tool.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public exports for conversation recall. | — |
| `types.py` | Core | Conversation search DTOs, index coverage metrics, limits (`MAX_SNIPPET_CHARS=700`, `MAX_EXPANDED_SNIPPET_CHARS=4000`), scope/lineage request fields, the `since`/`until` window contract (it bounds a conversation by the time of its most recent message, and an expand request ignores it) and source reference contracts. | ✅ |
| `format_output.py` | Core | Shared hit formatting, expanded view dynamic capacity scaling, recall redact → sanitize/preamble, and `conversation_history` sources emission. A search that finds nothing ends with a note naming the explicit `since`/`until` window it ran under (the window bounds a conversation by its most recent message, as `ConversationSearchRequest` defines it, and the note says so) and saying to retry without it, so a model does not conclude that a conversation outside the window, or one that continued past it, does not exist; an expand request reads no window and gets none. | ✅ |

## Key Dependencies

- `myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_formatting`
- `myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_no_result` (`describe_time_window`, the one renderer of a since/until window)
- `myrm_agent_harness.toolkits.memory.agent_surface.tool_result_sources`
