# conversation_search/

## Overview
Framework-level conversation recall toolkit. Provides conversation search DTOs and shared formatting helpers; the `ConversationSearchProtocol` contract lives in `protocols/conversation_search.py` and is implemented by the host. Agents reach it only through `memory_search_tool(corpus=sessions)`; there is no standalone LLM tool.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public exports for conversation recall. | — |
| `types.py` | Core | Conversation search DTOs, index coverage metrics, limits (`MAX_SNIPPET_CHARS=700`, `MAX_EXPANDED_SNIPPET_CHARS=4000`), scope/lineage request fields and source reference contracts. | ✅ |
| `format_output.py` | Core | Shared hit formatting, expanded view dynamic capacity scaling, recall redact → sanitize/preamble, and `conversation_history` sources emission. | ✅ |

## Key Dependencies

- `myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_formatting`
- `myrm_agent_harness.toolkits.memory.agent_surface.tool_result_sources`
