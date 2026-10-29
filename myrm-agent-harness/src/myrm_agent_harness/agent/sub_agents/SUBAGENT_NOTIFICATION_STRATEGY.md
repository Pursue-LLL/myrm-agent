# Subagent Notification Strategy

## Summary

Subagent completion uses **cache-safe delivery paths**: dynamic content never enters `SystemMessage`; the frozen system prefix stays stable for Prompt Cache.

| Path | Trigger | Delivery | Code |
|------|---------|----------|------|
| In-stream completion | Parent agent still streaming | SSE `SUBAGENT_COMPLETION` only; **no** message injection | `streaming/recovery/stream_recovery_continuation.py` |
| Background wakeup | A child nobody is waiting on completes while parent idle (`wait=false`, or a `wait=true` / `wait_children` child that outlived its caller's timeout) | User/HumanMessage with `<system_notification type='adaptive_wakeup_followup'>` + headless rerun (bounded by the wake budget; a spent budget or a user stop leaves the notice only) | `myrm-agent-server/.../adaptive_wakeup/service.py` |
| Active query | LLM needs result details | `subagent_control_tool` (action=list) | `meta_tools/spawn_subagent/` |

---

## Design Rules

1. **No dynamic `SystemMessage`** — subagent results must not append to the SystemMessage chain (see `PROMPT_CACHE_PRACTICE.md` §1253).
2. **In-stream: SSE-only** — `StreamRecoveryContinuation._handle_subagent_notifications()` emits the event and returns `False` (no new turn, no `HumanMessage` append).
3. **Background wakeup: user message** — `AdaptiveWakeupService.handle_settlement()` calls `ChatService.ensure_chat_and_append_user_message()` with the wrapped notification text (summary and error are bounded and XML-escaped); it reloads as HumanMessage on the next run. Only a followup starts a turn, and it runs as the chat's own agent.
4. **A cancelled child never wakes the parent** — `SubagentManager._cleanup_child` skips `trigger_async_wakeup` when the child status is `CANCELLED` (user Stop, parent cancel, graceful-cancel timeout). Failed, timed-out and budget-cancelled children still wake it. Pull-based notifications for the cancelled child are unchanged.
5. **A child someone is blocked on never wakes the parent** — `spawn_child(wait=True)` and `wait_children()` register their children in `SubagentManager.awaited_children` while they block, and `_should_wake_parent` skips `trigger_async_wakeup` for a registered child: its result goes to the waiter, and a wake turn would answer the same result twice. A wait that gives up at its timeout releases the child, so its later completion wakes the parent once.
6. **A result the parent read itself is not delivered again** — `subagent_control_tool(action=list)` returns the result of every settled child and `action=wait` returns the result of the settled child it waited for, so both report those task ids (final statuses only; a child waiting for approval resumes and settles again, and a wait that timed out while the child keeps running reports nothing) through `report_results_read` in `utils/runtime/wakeup_registry.py`. The server handler records them, and a queued wake turn whose every result was read does not start (no wake budget is spent). A result the parent did not read, or only some of the results a wake turn would deliver, still wakes it. The harness itself keeps no read state.
7. **LLM retrieval guidance** — system prompt (`sub_agents/prompts.py`) and tool descriptions (`delegate_task_tool`, `subagent_control_tool`) instruct the model to call `subagent_control_tool` (mode=list) for async results.

---

## Prefix Cache Impact

```
Tools → System (frozen) → Messages (dynamic)
                              ↑
                    subagent notifications land here only
```

- Tools + System prefix remain byte-identical across turns when tool list and system chain are stable.
- Wakeup notifications append to **Messages**, so only the tail of the conversation changes.

---

## Related Docs

- [SUB_AGENT_SYSTEM.md](SUB_AGENT_SYSTEM.md) §17 — async wakeup flow
- [PROMPT_CACHE_PRACTICE.md](../context_management/PROMPT_CACHE_PRACTICE.md) — Tools → System → Messages order
