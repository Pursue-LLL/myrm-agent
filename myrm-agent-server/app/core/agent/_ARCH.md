# agent/

## Overview

Server-side agent runtime helpers that bridge harness framework APIs with session and channel context.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `tool_description_locale.py` | Core | `resolve_agent_params_locale` for `GeneralAgentParams.locale`; `resolve_tool_description_locale` for harness LLM tool description SSOT (`memory_*`, `web_search_tool`). | ✅ |
| `run_activity.py` | Core | In-flight counter for agent runs `AgentGateway` does not count: `track_background_agent_run` wraps cron `AgentJobRunner.run`, kanban `KanbanTaskRunner.run`, IM channel `ChannelAgentExecutor` (per `process_stream` open) and approval-timeout auto-resume, eval `LocalEvalExecutor.execute`; `active_background_agent_runs` adds the running sub-agent tasks of the harness `ACTIVE_SUBAGENTS` registry (detached ones outlive their parent turn). `/api/v1/health/liveness` reports `busy` (`agents.backgroundRunCount`) while any is running so the hosted idle recycler never pauses the sandbox mid-run, and `POST /system/sandbox/recreate` (manual environment reset) refuses with 409 while any is running; `tests/architecture/test_agent_run_tracking.py` pins every `process_stream` call site. | ✅ |

## Dependencies

- `myrm_agent_harness.utils.locale::resolve_locale` (POS: shared locale string handling)
- `myrm_agent_harness.agent.sub_agents.manager::ACTIVE_SUBAGENTS` (POS: running sub-agent registry read by `run_activity.py`)
