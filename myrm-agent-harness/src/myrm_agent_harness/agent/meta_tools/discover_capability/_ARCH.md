# discover_capability/

## Overview
Unified Capability Discovery gateway. Indexes agent-bound searchable skills (MCP PTC + user skills) into a BM25 (lexical) search index. When bound skills exceed inline catalog capacity (`hidden_skill_count > 0`), ``sync_discover_capability_tool()`` registers the discovery tool (LLM-facing name: `skill_search_tool`); otherwise it removes it. Stream and HITL resume paths call the same sync when the bound-set fingerprint changes (`agent/_internals/skill_catalog_turn.py`).

**Query contract**: the index matches words in skill names and descriptions, and those are mostly English, so the description and the `query` argument ask for English keywords plus synonyms and do not promise that any language works. A miss names the retry (English keywords or synonyms) and, when skills are bound, how many skills `query='*'` would list; a hit ends with the same one-line retry, except the `*` listing itself. The `No capabilities found` prefix is stable for callers that test for it.

**Boundary**: searches the **agent-bound skill library**. External marketplace install uses ``skill_market_tool`` when **product Turn1-mount** enables it (`enable_skill_market` / market backend wired in server `tool_setup/skill.py`); otherwise the discovery tool description points users to Settings → Skills → Discover.

## MCP / OpenAPI overflow policy (SSOT)

**Current harness outcomes** — see ``TOOL_DESIGN_STRATEGY.md`` §2.5:

| Outcome | When |
|---------|------|
| **Direct FC Turn1** | Per-server schema ≤ `compute_direct_threshold()` (11,250 tok) **and** aggregate direct pool ≤ `AGGREGATE_DIRECT_TOKEN_BUDGET` (15,000 tok) |
| **MCP PTC** | Per-server schema > threshold **or** aggregate overflow (largest servers demoted first) |

Whether a further routing outcome is worth adding is under evaluation: `TOOL_DESIGN_STRATEGY.md` §10.2.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| discover_capability_tool.py | Core | Unified discovery meta-tool (LLM name: `skill_search_tool`), index sync, `<BoundSkills>` XML output with a one-line retry hint; description varies by `market_tool_mounted` and locale. | ✅ |
| capability_gap.py | Core | Substring trigger registry (`CAPABILITY_GAP_REGISTRY`, 14 IDs) for server preflight intent matching. A discover miss emits no gap blocks or SSE. | ✅ |

## Key Dependencies

- `backends`
- `toolkits`
- `agent.tool_management`
