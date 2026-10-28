# Subagent Notification Strategy

## Summary

Subagent completion uses **cache-safe delivery paths**: dynamic content never enters `SystemMessage`; the frozen system prefix stays stable for Prompt Cache.

| Path | Trigger | Delivery | Code |
|------|---------|----------|------|
| In-stream completion | Parent agent still streaming | SSE `SUBAGENT_COMPLETION` only; **no** message injection | `streaming/recovery/stream_recovery_continuation.py` |
| Background wakeup | `wait=false` child completes while parent idle | User/HumanMessage with `<system_notification type='adaptive_wakeup_followup'>` + headless rerun (bounded by the wake budget; a spent budget or a user stop leaves the notice only) | `myrm-agent-server/.../adaptive_wakeup/service.py` |
| Active query | LLM needs result details | `subagent_control_tool` (action=list) | `meta_tools/spawn_subagent/` |

---

## Design Rules

1. **No dynamic `SystemMessage`** — subagent results must not append to the SystemMessage chain (see `PROMPT_CACHE_PRACTICE.md` §1253).
2. **In-stream: SSE-only** — `StreamRecoveryContinuation._handle_subagent_notifications()` emits the event and returns `False` (no new turn, no `HumanMessage` append).
3. **Background wakeup: user message** — `AdaptiveWakeupService.handle_settlement()` calls `ChatService.ensure_chat_and_append_user_message()` with the wrapped notification text (summary and error are bounded and XML-escaped); it reloads as HumanMessage on the next run. Only a followup starts a turn, and it runs as the chat's own agent.
4. **A cancelled child never wakes the parent** — `SubagentManager._cleanup_child` skips `trigger_async_wakeup` when the child status is `CANCELLED` (user Stop, parent cancel, graceful-cancel timeout). Failed, timed-out and budget-cancelled children still wake it. Pull-based notifications for the cancelled child are unchanged.
5. **LLM retrieval guidance** — system prompt (`sub_agents/prompts.py`) and tool descriptions (`delegate_task_tool`, `subagent_control_tool`) instruct the model to call `subagent_control_tool` (mode=list) for async results.

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
