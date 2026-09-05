# routing/

## Overview
Inbound message processing pipeline: routing, commands, policy, sessions.

## Emoji Reaction Approval

Reaction-capable channels — Slack, Telegram, WhatsApp, Discord, Signal, Feishu,
iMessage, **Mattermost**, **Matrix** — convert inbound emoji reactions into
`InboundMessage(metadata={"reaction": True, "target_message_id": ...})`.

> **Invariant.** Every reaction inbound is built with `mentioned=True` so it
> survives `BaseChannel._emit_inbound`'s default `SELECTIVE_POLICY`
> (`group=MENTION_ONLY`). Reactions are precise, user-driven gestures aimed at
> a specific bot message, not group-chat noise — gating them on `@mention`
> would silently drop every group-chat approval. Pinned by
> `tests/channels/test_reaction_inbound_policy.py::TestReactionConstructionSiteContract`.

`parse_approval_command` (commands/commands.py) recognises a unified, three-tier
approval alphabet (skin-tone modifiers and Unicode variation selectors are
normalised away by `normalize_approval_emoji`):

| Decision        | Emojis                                         | Text aliases                                |
|-----------------|------------------------------------------------|---------------------------------------------|
| `allow_once`    | 👍, ❤, ✅, 🤝, 💪                              | `/approve`, `1`, `y`/`yes`, `ok`, 同意, 好的 |
| `allow_always`  | ♾️, ⭐                                         | `/approve-always`, `/always`, `aa`, `!y`, 永远允许 |
| `deny`          | 👎, ❌, 🚫                                      | `/deny`, `/deny <reason>`, `2`, `n`/`no`, 拒绝, 不行 |

`_is_reaction_approval_valid` in `commands/router_commands_approval.py` enforces a layered gate:
1. **Pending-approval check** — the chat must have an active interrupted task.
2. **Target match** — when the reaction carries `target_message_id`, it must
   equal the cached approval message id (`_approval_msg_ids`).
3. **Approver authorisation** — in **group chats**, the reacting `sender_id`
   must equal the original requester (`_ActiveTask.requester_id`) or appear in
   the configurable `approval_co_approvers` allow-list. DMs skip this step.

`_handle_approval_command` then converts the three-tier decision into the
exact payload `myrm-agent-harness.apply_approval_decisions` expects:

- `allow_once`   → `{"type": "approve"}`
- `allow_always` → `{"type": "approve", "extensions": {"allowAlways": True}}`
  — drives `add_to_allowlist_if_needed` once the channel agent executor has
  bound the user via `set_approval_user_id`.
- `deny`         → `{"type": "reject", "feedback": "Denied via {channel} channel command"}`
  — when the user provides a reason via `/deny <reason>` (capped at 280 chars),
  an additional `"guidance": "<reason>"` field is included; the harness injects
  it as a `HumanMessage` for the agent to course-correct. The IM status message
  also displays the reason (i18n key `approval_denial_with_reason_processing`).
  Without a reason, `guidance` is omitted and only the generic feedback is sent.

## ActionButton Callback Approval

`ApprovalRegistry.create_approval()` pushes `ActionButton`s (✅ Approve / ❌ Deny)
to IM channels when `chat.source != "web"`. Each channel encodes the
`action_id` (`approval:{approve|deny}:{record_id}`) into its native callback
format (Telegram `act:...`, Slack `block_actions`, Discord `custom_id`, etc.).

When the user clicks a button, the channel's inbound parser strips the
transport prefix and delivers `InboundMessage(content="approval:approve:{id}",
metadata={"callback_prefix": "act", "origin_message_id": ...})`.

`_consume_loop` in `router.py` intercepts this **before** `parse_approval_command`
(which only handles text/emoji input) with a dedicated guard:

```python
if msg.metadata.get("callback_prefix") == "act" and msg.content.startswith("approval:"):
    asyncio.create_task(self._handle_action_button_approval(msg))
```

`_handle_action_button_approval` in `commands/router_commands_approval.py` then:

1. **Parses** action (`approve`/`deny`) and `approval_id` from content.
2. **Authorises** — in group chats, only the original requester or a
   co-approver may resolve (same policy as reaction approval).
3. **Resolves** via `ApprovalRegistry.resolve_approval()` — only PENDING
   records are updated; already-resolved approvals return `None` and the
   handler exits (prevents status flip on duplicate button clicks).
4. **Edits** the original IM message to show `✅ Approved by @user` and
   prevent further confusion from stale buttons.
5. **Routes by type** — if `record.action_type == "outbound_draft"`, calls
   `_resolve_outbound_draft` to send or discard the held channel message
   (no LangGraph resume needed). Otherwise, **resumes** the interrupted
   LangGraph agent via `SessionGate.submit()` with a `resume_value`
   payload, or publishes `APPROVAL_RESOLVED` event if no active task
   exists in the router (e.g. WebUI concurrent resolve).

## `/new` Session Boundary Cleanup

`_handle_new_session` in `commands/router_commands_session.py` performs a three-phase cleanup
before marking the peer for a fresh Chat:

1. **Abort running task** — `_abort_session_task(state_key, …)` cancels
   `cancel_token`, the `asyncio.Task`, cleans up the placeholder, and clears
   `_approval_msg_ids`. This is the same helper used by `/stop`.
2. **Flush pending queue** — `SessionGate.clear_pending_for_key(state_key)`
   drops all queued inbound messages to prevent them from bleeding into the
   new session.
3. **Reset per-session flags** — YOLO mode (`_session_yolo`) and personality
   overrides (`_session_personality`) are cleared so the new session starts
   with default behaviour.

Only after cleanup does `handle_new_session` (commands/commands.py) flag the peer and
send the confirmation reply.

## Stuck Task Watchdog

`_janitor_loop` (60s interval) calls `_reap_stuck_tasks` to detect IM agent
tasks exceeding `_STUCK_TASK_TIMEOUT` (600s). For each stuck task:

1. **Cancel** — `cancel_token.cancel()` + `task.cancel()`.
2. **Resource cleanup** — stop typing indicators, clean up placeholder message
   with a localized timeout notification (`stuck_task_timeout_user_message`).
3. **State cleanup** — remove from `_active_tasks`, `_cleanups`, `_approval_msg_ids`.
4. **SessionGate release** — call `on_task_complete()` to unblock the session
   and allow pending messages to be processed.

This prevents semaphore exhaustion (max 5 concurrent tasks) and session
deadlocks when an agent execution hangs without crashing.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Inbound message processing pipeline: routing, commands, policy, sessions. | — |
| command_defs.py | Core | CommandDef data model, CommandAction/CommandKind enums, built-in SYSTEM_COMMANDS tuple (stop, new, compact, retry, undo, yolo, personality, bind, unbind, topic, goal, steer, queue, background, kanban, memory, learn, memo, review-week, handoff, status, help). | — |
| command_registry.py | Core | CommandRegistry: central O(1) lookup for slash commands. Validates names and prevents system command overwriting. | — |
| commands/（子包） | Core | 命令域子包：`commands.py`（参数解析 + 高层 handler）、`router_commands.py`（聚合 `RouterCommandsMixin`）、`router_commands_approval.py`（`/stop`、reaction/button approval）、`router_commands_session.py`（`/new`、`/compact`、`/retry`、`/undo`、topic）、`router_commands_modes.py`（`/yolo`、`/personality`、`/steer`、`/queue`）、`router_commands_goals.py`（`/goal`、`/subgoal`、`/background`、`/handoff`）、`router_commands_memory.py`（`/status`、`/kanban`、`/learn`、`/memory`）。`commands/__init__.py` 为聚合门面 | ✅ |
| context_buffer.py | Core | GroupContextBuffer: 结合持久化数据平面异步拉取与内存兜底的上下文缓冲。 | ✅ |
| graceful_degradation.py | Core | Graceful degradation controller for smooth quality adaptation. | ✅ |
| message_effects.py | Core | Message side-effect operations (typing/keepalive, reactions, placeholder, reply, busy ack). `edit_placeholder` uses `render()`; `edit_progress` caps preview via `cap_stream_preview()`. | ✅ |
| placeholder_strategy.py | Core | Adaptive placeholder defer (180ms) and short-circuit for fast replies; eager materialize on stream activity. | ✅ |
| policy_resolver.py | Core | Policy resolution module extracted from Router core routing logic. Guest mode requires `explicit_mention` metadata (entity-based only; reply-to-bot does not bypass non-enabled groups). | ✅ |
| policy_resolver_support.py | 辅助 | BoundedCooldownMap + GroupFollowUpTracker helpers for PolicyResolver. | ✅ |
| retry_policy.py | Core | Generic retry policy component with exponential backoff, circuit breaker integration, | — |
| router.py | Core | Core inbound message routing loop. After approval/reaction/slash filtering, checks active task `busy_input_mode` (steer/redirect auto-dispatch), applies inbound risk gate (symmetric with outbound risk gate in bus.py), dispatches cron event triggers via `inbound_event_dispatch` then submits to SessionGate. | ✅ |
| router_constants.py | Core | Constants and pure helpers shared by routing modules. Includes silence reassurance thresholds and `_is_silent_content` outbound filter. Unit tests can import directly. | — |
| router_execution.py | Core | `RouterExecutionMixin` is composed into `AgentRouter` via multiple inheritance; `_prepare_execution_context` rejects search-track `route_agent_id` (external CLI aliases like `claude` unchanged); `_deliver_agent_result` auto-attaches WebUI handoff deep link button for IM channel replies and intercepts outbound messages as draft ApprovalRecord when `topic_ctx.reply_mode == "draft_review"` (Channel Outbound HITL). | — |
| router_host.py | Core | Typing protocols: host instance attributes required by Router Mixins. | ✅ |
| router_keys.py | Core | ``routing_session_key`` builds ``f"{channel}:{peer_id}"`` for DM/group peer maps | — |
| router_models.py | Core | Data models referenced by AgentRouter in router.py and commands/ (_ActiveTask with steering_token, `requester_id` for reaction approval auth, `locale` for stuck watchdog i18n, ReactionPolicy, etc.) | — |
| router_stream.py | Core | RouterStreamMixin composed into AgentRouter (router.py) via multiple inheritance; includes edit-in-place heartbeat loop for long-task silence detection (sends once, then edits the same message with elapsed time). | — |
| router_stream_scrubber.py | Core | Stream content and progress scrubbing utilities: filters `<think>` tags and normalizes raw tool executions into user-friendly Stage descriptions. | ✅ |
| router_stream_throttle.py | Core | Pure time-interval checks for placeholder progress edits during execute_stream. | ✅ |
| channel_data_plane.py | Core | ChannelDataPlaneService: 渠道入站脱敏持久化、上下文拉取、知识提取自适应打标与自产回复追溯。 | ✅ |
| session_gate.py | Core | Sits between Router's consume loop and the per-message handler. Supports optional `on_busy_ack` callback (30s debounce) for immediate user feedback when messages are queued or dropped. | ✅ |
| session_rate_limiter.py | Core | Session-level rate limiting for single-instance self-protection. | ✅ |
| stream_config.py | Config | Unified configuration for streaming components. | ✅ |
| stream_manager.py | Core | Streaming optimization components used by Router for intelligent updates. | ✅ |
| stream_metrics.py | Core | Provides observability into streaming quality via tracing infrastructure. | ✅ |

## Channel agent bind (`/bind`)

`/bind` persists via `SqlTopicManager.bind_topic` (SSOT). Search-track agents (`prompt_mode=search`) are rejected with `topic_search_agent_rejected` i18n — same rule as Settings channel routing API. Legacy Search binds are purged at `resolve_topic` / `get_all_topics` read time.

## Key Dependencies

- `infra`
- `utils`
