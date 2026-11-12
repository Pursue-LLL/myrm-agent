# memory_context/

## Overview

User memory injection into model calls — `<user_memory_context>` with a scope
boundary; reuses `memory_brief_snapshot` to avoid preview/execution drift;
records injection/budget telemetry for the server. The block is request-local:
rebuilt for every model call from the turn's memory context (the prefetched
snapshot, or one `manager.get_context` load per turn), never written to the
thread, and recognised by a message flag rather than by its text. Stored values
reach it with every tag opener neutralised, and learned facts stay out of it
(the model retrieves them through `memory_search_tool`).

Detailed design: [MIDDLEWARE_SYSTEM.md](../MIDDLEWARE_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public export for `MemoryContextMiddleware`. | — |
| `memory_context_middleware.py` | Core | `<user_memory_context>` + scope boundary; `memory_brief_snapshot` reuse (a run without a snapshot loads `manager.get_context` on the turn's first model call and the turn's later calls reuse it, so a memory saved mid-turn reaches the next turn and a failed load is not retried within the turn; a turn starts at the user's own latest message in the thread, so neither a notice the runtime appends nor a rewrite an outer middleware makes to the request starts one); the block is rebuilt per model call and inserted into the request only (per-call tool guidance goes into a copy of the context, neither the snapshot nor the loaded context is written), skipped with a warning when the request already carries a flagged block; injection/budget telemetry via API hooks (budget carries the characters the block's sections use of the block budget and the configured/injected rule counts, veto and behavioral, so trimmed rules are visible to the client). | ✅ |
| `memory_context_format.py` | Internal | Renders the head memory block from the stored memory and returns it as a `MemoryBlock` (text, characters used, rules configured and injected): every stored value goes through `defang_markup`; every rule is one `When: … → Do: …` line of a single `Behavioral Rules` section, in the order storage hands the rules over, and a rule whose action holds a standalone prohibition word is pinned against the budget cut; the scope boundary says which of two conflicting rules wins whenever the block carries rules; the search-guidance tail closes the block; the message constructor and the `memory_context` flag check that identify the block; per-turn knowledge-base snippets are not part of it. | ✅ |
| `memory_context_budget.py` | Internal | One char budget over the memory sections (`render_budgeted_sections`, which charges a section's pinned items first so a cut drops the others, and reports the characters the kept sections use) and its limit (`MEMORY_BLOCK_MAX_TOKENS`, `MEMORY_BLOCK_BUDGET_CHARS`), `bound_tool_names` (the one reader of the tool names a request binds), `defang_markup` (rewrites every tag opener, ASCII and look-alike, to `&lt;` and leaves `&`, `>` and code untouched), `escape_xml_item` (full XML escaping, used by the knowledge pack), the search-guidance and cold-start prompt texts. | ✅ |
| `proactive_pack_middleware.py` | Core | Per-turn knowledge pack: renders the snippets the server passes in the run context (`PROACTIVE_PACK_CONTEXT_KEY`) as one untrusted-data block, memoized per turn so every model call of the tool loop sends the same bytes, and appends it to the tail of the final HumanMessage; follows the memory switches (no manager or `RecallMode.TOOLS` skips); nothing is persisted to the thread. | ✅ |
| `ephemeral_delta_middleware.py` | Core | Human-tail injection via `toolkits.memory.ephemeral_delta` SSOT store; runs after `memory_context_middleware`. | ✅ |

## Key Dependencies

- `agent.memory` — memory manager
- `core.message_origin` — tells the user's own message from one the runtime appended (the turn's identity)
- `langchain_core.messages` — message models
