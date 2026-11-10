# middlewares/

## Overview

Agent middleware system exports. Provides the complete middleware stack (context management, debug logging, tool interception).

Detailed design: [MIDDLEWARE_SYSTEM.md](MIDDLEWARE_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public middleware exports. | ✅ |
| `_session_context.py` | Internal | Shared ContextVars for the middleware chain; `isolated_terminal_errors()` gives a nested child run a registry of its own. | ✅ |
| `_run_workspace.py` | Internal | `run_workspace`: the `workspace_path` in the LangGraph `Runtime` context a hook receives; shared by `progress_middleware` and `CompletionGuard`. | ✅ |
| `_run_notices.py` | Internal | Request-local notices of one run: `run_scope` (the per-run dict a request carries), `frozen_for_run` (renders a notice on the run's first request and hands back that one rendering on every later request) and `NoticeLedger` (append-only notices, each placed behind the message that was last when it was written). Within a run every request extends the one before it, because the provider caches the request prefix and a signed reasoning block is valid only for the prefix it was written under; the todo focus and the circuit-breaker constraints use it. | ✅ |
| `advisor_risk_trigger_router.py` | Core | Adaptive risk-triggered router for MoA advisor overlay — gates advisor fan-out based on ReplanMiddleware errors, LoopGuard telemetry, fatal error bypass, and immunity/quota gates. | ✅ |
| `clarification_guard_middleware.py` | Core | Enforces single `ask_question_tool` call per turn; answers coexisting or duplicate tool calls with synthetic error ToolMessages (the calls stay in the AI message, so the model reads why they did not run). | ✅ |

| `debug_logger_middleware.py` | Core | Full message list debug logging. | ✅ |
| `plan_confirm_middleware.py` | Core | Plan-phase HITL: intercept first plan and major re-plans via `interrupt()` with 3+ items for user review. | ✅ |
| `progress_middleware.py` | Core | Active todo focus on the tail of the user's own latest message (never on a runtime notice behind it), rendered on the run's first request and shown unchanged on every later one so the cached prefix survives; only for an agent that holds `todo_write`. | ✅ |
| `goal_focus_middleware.py` | Core | ACTIVE goal objective on the tail of the user's own latest message; the line is the same on every request of a run. | ✅ |
| `moa_advisor_middleware.py` | Core | Agent-loop MoA advisor overlay — ref fan-out, cache-safe transient prompt tail injection with KV-cache preservation, skip SSE for budget pressure and insufficient refs (`moa_overlay_skipped`), supports injected `privacy_redactor` for reference PII/secret scrubbing. | ✅ |
| `model_call_cancel.py` | Core | Outermost model-call wrapper (first in `build_middlewares`): a Stop while the request is in flight aborts it within one poll interval (`run_until_cancelled`) and raises `OperationCancelledError`, which the stream executor leaves as a Stop, not as a model failure. | ✅ |
| `parallel_tool_calls.py` | Core | `ParallelToolCallsMiddleware`: when `EngineParams.enable_parallel_tool_calls` is set, every model call that offers tools carries `parallel_tool_calls` in `ModelRequest.model_settings` (a setting the request already carries is kept; a call without tools gets none); wired behind every middleware that rewrites the request and ahead of the two guard wrappers below, so a failover rebuild of the graph applies it to the new model too. | ✅ |
| `thinking_replay_guard_middleware.py` | Core | `ThinkingReplayGuardMiddleware`: when the provider refuses replayed signed reasoning (`FailoverReason.THINKING_SIGNATURE`), the request is sent once more with every block removed, and the run replays none afterwards (the choice lives in the run dict, so the next run replays again). The executor-level one-shot recovery stays behind it as the last resort. | ✅ |
| `request_view_guard_middleware.py` | Core | `RequestViewGuardMiddleware`: the last model-call wrapper before the provider; hands the digests of the request's messages to the run's cache break detector, which names the first message where a request stopped extending the previous one. Records only, never rewrites. | ✅ |
| `rate_limit.py` | Core | Proactive provider 429 throttling. | ✅ |
| `replan_middleware.py` | Core | Dynamic replan loop on tool errors. | ✅ |
| `session_access_middleware.py` | Core | Inject the directory access context (`<session-access>` block: the workspace, the declared roots and the session's HITL grants) before a model call when the history does not carry it yet (marker dedup); returns only the new message. Only a run whose registry holds a tool taking paths (`glob_tool`, `grep_tool`, `file_write_tool`, `file_edit_tool`, `bash_code_execute_tool`) gets it, read per call because the registry is filled after the chain is built: the fast-search mount carries `file_read_tool` alone, over spill files and uploads whose paths the messages state in full. | ✅ |
| `subagent_limit_middleware.py` | Core | Max concurrent subagents per turn. | ✅ |

| Submodule | Description |
|-----------|-------------|
| `completion/` | Finish gate, verification checklist, external evidence, deliverable write checks, execution-claim grounding, and per-turn evidence disclosure. See [completion/_ARCH.md](completion/_ARCH.md). |
| `approval/` | HITL approval queue, batch, scheduler. See [approval/_ARCH.md](approval/_ARCH.md). |
| `guardrails/` | Guardrail provider chain + GuardrailMiddleware. See [guardrails/_ARCH.md](guardrails/_ARCH.md). |
| `tooling/` | Single interception point for all tool calls: interceptor, executor, history hygiene, dangling-call repair, skill attenuation, and their guards/helpers. See [tooling/_ARCH.md](tooling/_ARCH.md). |
| `context_pipeline/` | Request-time context assembly and budget (compression intent, cache feedback, schema fingerprint). See [context_pipeline/_ARCH.md](context_pipeline/_ARCH.md). |
| `memory_context/` | User memory injection into model calls (`<user_memory_context>`, scope boundary, per-turn knowledge pack, telemetry). See [memory_context/_ARCH.md](memory_context/_ARCH.md). |
| `concurrency/` | Subagent semaphore limits and the tool conflict gate (concurrency-safe calls share, every other call runs alone). See [concurrency/_ARCH.md](concurrency/_ARCH.md). |
| `security/` | Security enforcement middleware: boundary rules injection + eight-layer guardrail defense. See [security/_ARCH.md](security/_ARCH.md). |

## Key Dependencies

- `agent/context_management/` — context pipeline processors
- `agent/security/` — tool result validation, guards
- `infra`
- `observability`
- `toolkits`
- `utils`
