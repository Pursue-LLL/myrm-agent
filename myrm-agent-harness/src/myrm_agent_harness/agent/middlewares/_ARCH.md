# middlewares/

## Overview

Agent middleware system exports. Provides the complete middleware stack (context management, debug logging, tool interception, filesystem search).

Detailed design: [MIDDLEWARE_SYSTEM.md](MIDDLEWARE_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public middleware exports. | ✅ |
| `_session_context.py` | Internal | Shared ContextVars for the middleware chain; `isolated_terminal_errors()` gives a nested child run a registry of its own. | ✅ |
| `_run_workspace.py` | Internal | `run_workspace`: the `workspace_path` in the LangGraph `Runtime` context a hook receives; shared by `progress_middleware` and `CompletionGuard`. | ✅ |
| `_message_origin.py` | Internal | `is_user_authored_human_message`: tells a HumanMessage the user wrote from one the runtime injected (`is_system_synthetic`); shared by the approval and security middlewares. | ✅ |
| `advisor_risk_trigger_router.py` | Core | Adaptive risk-triggered router for MoA advisor overlay — gates advisor fan-out based on ReplanMiddleware errors, LoopGuard telemetry, fatal error bypass, and immunity/quota gates. | ✅ |
| `clarification_guard_middleware.py` | Core | Enforces single `ask_question_tool` call per turn; answers coexisting or duplicate tool calls with synthetic error ToolMessages (the calls stay in the AI message, so the model reads why they did not run). | ✅ |

| `debug_logger_middleware.py` | Core | Full message list debug logging. | ✅ |
| `filesystem_search_middleware.py` | Core | Inject glob/grep workspace search tools. | ✅ |
| `plan_confirm_middleware.py` | Core | Plan-phase HITL: intercept first plan and major re-plans via `interrupt()` with 3+ items for user review. | ✅ |
| `progress_middleware.py` | Core | Append-Only active todo focus injection into current HumanMessage (SystemMessages behind it, such as the boundary rules, are skipped) with KV cache preservation; only for an agent that holds `todo_write`. | ✅ |
| `goal_focus_middleware.py` | Core | ACTIVE goal objective injection into last HumanMessage. | ✅ |
| `moa_advisor_middleware.py` | Core | Agent-loop MoA advisor overlay — ref fan-out, cache-safe transient prompt tail injection with KV-cache preservation, skip SSE for budget pressure and insufficient refs (`moa_overlay_skipped`), supports injected `privacy_redactor` for reference PII/secret scrubbing. | ✅ |
| `model_call_cancel.py` | Core | Outermost model-call wrapper (first in `build_middlewares`): a Stop while the request is in flight aborts it within one poll interval (`run_until_cancelled`) and raises `OperationCancelledError`, which the stream executor leaves as a Stop, not as a model failure. | ✅ |
| `rate_limit.py` | Core | Proactive provider 429 throttling. | ✅ |
| `replan_middleware.py` | Core | Dynamic replan loop on tool errors. | ✅ |
| `session_access_middleware.py` | Core | Inject per-turn HITL session directory access context (`<session-access>` block) before a model call when the history does not carry it yet (marker dedup); returns only the new message. | ✅ |
| `subagent_limit_middleware.py` | Core | Max concurrent subagents per turn. | ✅ |
| `sync_hook_parity.py` | Internal | `apply_sync_hook_parity()` gives each middleware that defines only the async `awrap_tool_call`/`awrap_model_call` a pass-through sync variant, so sync ToolNode paths don't raise. It moves the instance onto a cached subclass of its own class: LangChain reads `before_model`/`after_model` (graph nodes) from the class, so a forwarding wrapper object would hide them. | ✅ |

| Submodule | Description |
|-----------|-------------|
| `completion/` | Finish gate, verification checklist, external evidence, deliverable write checks, execution-claim grounding, and per-turn evidence disclosure. See [completion/_ARCH.md](completion/_ARCH.md). |
| `approval/` | HITL approval queue, batch, scheduler. See [approval/_ARCH.md](approval/_ARCH.md). |
| `guardrails/` | Guardrail provider chain + GuardrailMiddleware. See [guardrails/_ARCH.md](guardrails/_ARCH.md). |
| `tooling/` | Single interception point for all tool calls: interceptor, executor, history hygiene, dangling-call repair, skill attenuation, and their guards/helpers. See [tooling/_ARCH.md](tooling/_ARCH.md). |
| `context_pipeline/` | Request-time context assembly and budget (compression intent, cache feedback, schema fingerprint). See [context_pipeline/_ARCH.md](context_pipeline/_ARCH.md). |
| `memory_context/` | User memory injection into model calls (`<user_memory_context>`, scope boundary, untrusted wrapping, telemetry). See [memory_context/_ARCH.md](memory_context/_ARCH.md). |
| `concurrency/` | Subagent semaphore limits and the tool conflict gate (concurrency-safe calls share, every other call runs alone). See [concurrency/_ARCH.md](concurrency/_ARCH.md). |
| `security/` | Security enforcement middleware: boundary rules injection + eight-layer guardrail defense. See [security/_ARCH.md](security/_ARCH.md). |

## Key Dependencies

- `agent/context_management/` — context pipeline processors
- `agent/security/` — tool result validation, guards
- `infra`
- `observability`
- `toolkits`
- `utils`
