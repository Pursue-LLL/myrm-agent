# agent/_factory/

## Overview
SkillAgent factory assembly — MCP routing, surface mode, OpenAPI direct bind, and `create_skill_agent` pipeline.

## MCP routing (current outcomes: Direct FC, MCP PTC)

| File | Role | Description |
|------|------|-------------|
| `__init__.py` | Package | SkillAgent factory assembly package marker. |
| `mcp_routing.py` | Core | **Direct FC** vs **MCP PTC** by per-server schema + aggregate budget (`AGGREGATE_DIRECT_TOKEN_BUDGET=15_000`). Connects to all MCP servers in parallel (`asyncio.gather`), serializes configs via `mcp_config_to_runtime_dict` SSOT, and clears active MCP entries in `skill_registry` before routing. Returns `MCPRoutingResult(skills, direct_tools)`; Direct FC tools are wrapped with the same shared explicit `cache_ttl_seconds` + `cacheable_tools` result cache used by PTC, without changing the route. |
| `mcp_surface.py` | Core | `MCPSurfaceMode`: `auto` \| `direct_fc`. `direct_fc` forces all MCP servers into direct Turn1 FC regardless of per-server or aggregate token thresholds. Legacy `catalog_invoke` profile values parse as `auto` with warning. |
| `one_time_work.py` | Core | `start_one_time_work(shell_tools=...)`: starts the token-vocabulary load (once per process) and, with the bash tool mounted, the Python toolchain probe on background threads without waiting, so the first reader of each finds it built or waits for the build already running instead of building it ahead of the first model request. |
| `builder.py` | Core | Wires routing into `create_skill_agent`, which first calls `executor.warm_up()` and `start_one_time_work()` so the rest of the assembly and the first model request hide the one-time setup. Turn1 mount via `file_access_mode` (FileAccessMode SSOT). Clears MCP registry when `mcp_servers` is empty. Wires dedicated/fallback compactor LLM (`summarizer_llm`) into context pipeline middleware. OpenAPI direct bind raises `ConfigIncompleteError` when enabled services produce zero tools or schema exceeds aggregate budget. Maps the user-facing turn budget `spec.max_iterations` to `2 * max_iterations` LangGraph nodes (1 turn = model + tools nodes), aligned with subagent `max_turns * 2`. |

```
route_mcp_servers()
  ├─ clear_mcp_skills() in skill_registry
  ├─ per-server schema > direct_threshold → MCP PTC
  ├─ aggregate direct pool > 15K tok (auto) → demote largest servers → MCP PTC
  └─ else → Direct FC Turn1 bind

create_skill_agent() OpenAPI path
  ├─ enabled services but 0 tools loaded → ConfigIncompleteError (openapi_load_failed)
  ├─ schema ≤ 15K tok → Turn1 direct tools
  └─ schema > 15K tok (non direct_fc) → ConfigIncompleteError (openapi_direct_budget_exceeded)
```

Routing policy and why blind-call gateways and tool-level deferral are not offered: `TOOL_DESIGN_STRATEGY.md` §2.5 and §10.2.

## Verification

| Layer | Tests |
| --- | --- |
| Unit | `tests/agent/_factory/test_builder_openapi_load_failed.py`, `test_builder_openapi_budget.py`, `test_builder_mcp_registry_clear.py`, `test_builder_executor_warm_up.py`, `test_one_time_work.py` |
| Integration | `tests/integration/test_openapi_fail_loud_integration.py` |
| Architecture gate | `tests/architecture/test_openapi_fail_loud_gate.py`, `test_mcp_routing_two_outcomes.py` |
| Chrome E2E (server) | `myrm-agent-server/tests/e2e/test_openapi_fail_loud_chrome_e2e.py` — load_failed + budget_exceeded UI SSE |
