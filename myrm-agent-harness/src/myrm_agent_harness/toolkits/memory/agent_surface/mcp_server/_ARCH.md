# mcp_server/

## Overview

MCP adapter exposing `MemoryManager` to external agents as `memory_recall`, `memory_list`, `memory_store` and
`memory_manage`; the manager is resolved per request (ContextVar → resolver → default), and the default is
optional so a server whose requests all bind their own manager needs no storage at construction. Detailed design:
[MEMORY_SYSTEM.md](../../MEMORY_SYSTEM.md).

## File Index

| File | Role | Description | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | Facade | Public entry: `MemoryMCPServer`, `create_memory_mcp_server`, per-request context setters. | ✅ |
| `server.py` | Core | `MemoryMCPServer` (tool registration, manager resolution, Streamable HTTP app; the default manager is optional, in which case `approval_required` is stated explicitly) and its factory. | ✅ |
| `request_context.py` | Util | ContextVar bindings for the request's `MemoryManager` and the wiki-boundary flag. | ✅ |
| `common.py` | Util | `CATEGORY_TO_TYPE`, `parse_string_list`, `ManagerResolver`. | ✅ |
| `recall_tool.py` | Core | `memory_recall`: semantic search, profile lookup, budgeted and sanitized rendering. | ✅ |
| `list_tool.py` | Core | `memory_list`: category overview and paginated enumeration. | ✅ |
| `store_tool.py` | Core | `memory_store`: validation, wiki boundary, per-category writes that follow the manager's approval switch (the result tells a stored memory from one submitted for approval); knowledge/event gates follow the manager's enabled types, so an embeddings-less deployment stores through the BM25 mirror; a knowledge `importance` outside 0.0-1.0 is refused before the write (other categories ignore the score and never fail on it), and the `importance` argument carries the shared scope note so a client listing only the arguments sees it is knowledge-only. | ✅ |
| `manage_tool.py` | Core | `memory_manage`: MCP binding over `../memory_manage_core.py` (rate / delete / update / correct by memory id). | ✅ |

## Key Dependencies

- `../_memory_agent_tool_descriptions.py` (store/manage descriptions, `surface="mcp"`)
- `../memory_recall_formatting.py`, `../memory_recall_budget.py`, `../wiki_memory_boundary.py`, `../write_failure_feedback.py`
- `../../manager.py`, `../../types/`
- External libraries: `mcp`, `starlette`
