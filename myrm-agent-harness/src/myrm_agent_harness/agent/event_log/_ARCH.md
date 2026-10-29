# event_log/

## Overview
Complements Checkpointer with full event history. Optional — omitting `event_log_backend` leaves agent behaviour unchanged.

Detailed design: [EVENT_LOG_SYSTEM.md](EVENT_LOG_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Complements Checkpointer with full event history. Optional — omitting `event_log_backend` leaves agent behaviour unchanged. | ✅ |
| analytics.py | Core | Designed for separation of concerns: | ✅ |
| analytics_queries.py | Core | Read-side analytics helpers for ``EventLogger``. | ✅ |
| cli_summary.py | Core | Session-close summary table printed for developers (`generate_cli_summary`); renders a `SessionSummary` and reads the keys that `TokenTracker.to_dict()` and `TaskMetrics.to_dict()` export in its `token_economics` and `task_metrics`. | ✅ |
| integrity_gate.py | Core | Session enclosure and anti-silent-corruption verification gate (assert_log_integrity, verify_session_enclosure, verify_sequence_continuity). Applied on `FileEventLogBackend.get_events` reads and by the runtime invariant pack, not on logger close. | ✅ |
| logger.py | Core | Integration façade. Injected into BaseAgent via ``event_log_backend`` param. Persists error events from `stream_executor._emit_fatal_error` and `run_agent_loop`'s outer except (fault_side/error_kind/diagnostic_result/recovery_actions) so trace reconstruction sees LLM fatal errors. Redacts every event payload through `_sanitize.py` before persistence, the `security_audit` event written at close included: a decision quotes what it stopped, such as a blocked URL with its userinfo and query. Implements non-destructive safe field capping (<=64KB) and never re-reads the log on close (it sits on the user-visible path). | ✅ |
| protocols.py | Core | Protocol contract (EventLogBackend, FlushableEventLogBackend, get_latest_custom_state). Framework provides FileEventLogBackend; | ✅ |
| trace_builder.py | Core | Read-side aggregation logic. Merges llm_request + token_usage into LLMCallRecord with start/end times, prompt_preview, attempt, and retry_count. Aggregates custom_states and custom_messages extension inspection. Evaluates pure heuristic anomaly detection (tool_loop, token_surge, retry_backoff). Propagates fault-side attribution (fault_side/error_kind/recovery_actions/diagnostic_result) into error entries and ToolCallRecord, and computes the first-irrecoverable point. Pairs tool_start/tool_end by tool_call_id. | ✅ |
| _common.py | Core | Shared helpers (`_str_or_none`, `_int_or_zero`) and the `_EVENT_META_KEYS` bookkeeping-key set used to strip event metadata from `input_data`. | ✅ |
| _sanitize.py | Core | Write-side redaction of an event payload (`sanitize_event_data`): masks secrets in nested dict/list/tuple values through the shared walker `core/security/redact/nested.py`; a string under a key whose last word is `command` or `cmd` (`command`, `verify_command`, `rerun_cmd`) is masked as a command line first, because the leak detector reads the value after `--key` or `--auth` as an ordinary word. The value of a credential-named field (`Cookie`, `Authorization`, `password`, `db_password`) is masked by its name through `redact_field_text`, because a cookie or a bare password has no shape the leak detector knows; a variable reference such as `${API_KEY}` stays readable. The walker stops at 32 levels (a deeper container becomes `[nesting too deep]`) and where a container holds itself (it becomes `[circular reference]`); every other text goes through both redactors, the leak detector (token shapes, high-entropy strings, PEM blocks) and `redact_sensitive_text` (assignments such as `DB_PASSWORD=…`, `Cookie:` header lines), because neither finds what the other does; the scan costs about 1.2 ms per KB of text per event, linear in the size of the largest field (a 1 MB argument takes 1.3 s, 0.34 s with the leak detector alone); an event whose serialized line exceeds the file backend's `max_line_bytes` (100 KB) is replaced by a marker after the scan, so the scan of such an event is spent for nothing; and a payload that cannot be redacted is replaced by `{"_redaction_failed": true}` instead of being written as it is. | ✅ |
| _pairing.py | Core | Tool-call pairing state machine: `_PendingTool` tracks a `tool_start` awaiting its terminal event; `_pop_pending` prefers exact `tool_call_id` match. | ✅ |
| _llm.py | Core | LLM call aggregation: `_PendingLLMRequest` queues each `llm_request`; `_handle_token_usage` pairs it FIFO with the next `token_usage` event, extracting attempt and retry_count into `LLMCallRecord`. | ✅ |
| _tasks_steps.py | Core | Merges streaming `tasks_steps` progress events into the trace. | ✅ |
| _context_doctor.py | Core | Pure function token breakdown (system, chat, tool, file) and hotspot analyzer for execution traces. | ✅ |
| llm_observability.py | Core | Passive llm_request event recording with truncated prompt preview for replay. | ✅ |
| trace_types.py | Config | TraceAnomaly data structure for heuristic diagnosis. LLMCallRecord includes attempt and retry_count. ToolCallRecord carries fault_side + tool_call_id/message_id; ExecutionTrace carries anomalies, custom_states, custom_messages, and first_irrecoverable_index/timestamp. | ✅ |
| types.py | Config | Single source of truth for event log data structures, including CustomStatePayload and CustomMessagePayload, and the allowlist of persisted event types (the completion guard's `completion_guard` decisions among them: reason names and counts only). | ✅ |

| Submodule | Description |
|-----------|-------------|
| backends/ | Event log backends — built-in storage implementations (JSONL file: append, read, age-based cleanup, per-session removal). |
| dataset_export/ | Export pipeline — convert traces to ShareGPT/Alpaca/OpenAI JSONL with credential masking, PII redaction, quality filtering, and dedup. |
| `durable_atomic_writer.py` | Core | Durable atomic writer with short-write defense, advisory locking, and fsync. | ✅ |
| `torn_tail_repairer.py` | Core | Torn tail detection and self-repair engine for append-only event logs. | ✅ |

## Key Dependencies

- `core` (security redaction and leak detection)
- `infra`
- `utils`
