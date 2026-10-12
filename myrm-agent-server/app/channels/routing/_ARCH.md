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

Approval requests reach IM chats as `ActionButton`s whose `action_id` is
`approval:{approve|deny}:{record_id}`. Two senders produce them:

- `ApprovalRegistry.create_approval()` posts an approval block into the chat the
  request belongs to (`chat.source != "web"`).
- The notification dispatcher's owner card (`core/notifications/approval_card.py`)
  attaches buttons only for `APPROVAL_CLICK_CHANNELS` (Telegram). Other channels
  get a localized "open the app" hint, since their clicks never reach this handler.

Telegram's inbound parser is the only one that turns a click into
`InboundMessage(content="approval:approve:{id}", metadata={"callback_prefix": "act",
"origin_message_id": ...})`. No other provider sets `callback_prefix`, so clicks
on other channels never reach the guard below.

`_consume_loop` in `router.py` intercepts this **before** `parse_approval_command`
(which only handles text/emoji input) with a dedicated guard:

```python
if msg.metadata.get("callback_prefix") == "act" and msg.content.startswith("approval:"):
    asyncio.create_task(self._handle_action_button_approval(msg))
```

`_handle_action_button_approval` in `commands/router_commands_approval.py` then:

1. **Parses** action (`approve`/`deny`) and `approval_id` from content.
2. **Authorises**:
   - a held reply (`action_type == "outbound_draft"`) may only be decided by the
     owner (`_check_admin_permission`, see *Owner Check*); anyone else gets the
     localized `approval_requires_admin` reply and the record stays pending;
   - every other approval keeps the group rule: in group chats only the original
     requester or a co-approver may resolve (same policy as reaction approval),
     DMs skip it.
3. **Resolves** via `ApprovalRegistry.resolve_approval()` — only PENDING
   records are updated; already-resolved approvals return `None` and the
   handler exits (prevents status flip on duplicate button clicks).
4. **Edits** the original IM message to the localized status line
   (`approval_resolved_approved` / `approval_resolved_denied`, e.g. "Approved by
   @user") so stale buttons stop inviting clicks.
5. **Routes by type** — if `record.action_type == "outbound_draft"`, calls
   `_resolve_outbound_draft` to send or discard the held channel message
   (no LangGraph resume needed). Otherwise, **resumes** the interrupted
   LangGraph agent via `SessionGate.submit()` with a `resume_value`
   payload, or publishes `APPROVAL_RESOLVED` event if no active task
   exists in the router (e.g. WebUI concurrent resolve).

## Owner Check

`is_admin_sender(pairing, msg)` (policy_resolver_support.py) is the single rule
for "is this the sandbox owner": a control-plane-forwarded message
(`metadata["trusted_inbound"] == "control_plane"`) or a sender whose active
pairing role is ADMIN. A DM sender is not automatically the owner — an open DM
policy admits any account.

`AgentRouter._check_admin_permission` wraps it and fails closed (a lookup error
denies, because the consume loop has no per-message guard). It gates:

- commands declared `requires_admin` (`/yolo`, `/bind`), in DMs and groups alike;
- decisions on held replies (button path above).

Commands are dispatched before `PolicyResolver`, so the check sees the raw
`msg.sender_id`.

## Held Replies (`reply_mode=draft_review`)

`TopicContext.holds_reply_for_review` is the single predicate for every stage
that could expose a reply before a human approved it. While it holds,
`_consume_executor_stream(hold_reply=True)` never edits streamed text into the
placeholder (progress updates still show) — resumed turns included, which is why
the flag is separate from `topic_context` — and `_deliver_agent_result` turns the
final reply into an `outbound_draft` approval; nothing is sent until the owner approves it.

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

`_janitor_loop` runs `_janitor_sweep` every `_JANITOR_INTERVAL` (60s). A sweep
evicts expired callbacks, streaming sessions and stale session state, then
calls `_reap_stuck_tasks` to detect IM agent tasks exceeding
`_STUCK_TASK_TIMEOUT` (600s). The janitor is the only evictor of that state, so
a sweep that raises is logged at ERROR and the next cycle retries; only
cancellation ends the loop. For each stuck task:

1. **Cancel** — `cancel_token.cancel()` + `task.cancel()`.
2. **Resource cleanup** — stop typing indicators, clean up placeholder message
   with a localized timeout notification (`stuck_task_timeout_user_message`).
3. **State cleanup** — remove from `_active_tasks`, `_cleanups`, `_approval_msg_ids`.
4. **SessionGate release** — call `on_task_complete()` to unblock the session
   and allow pending messages to be processed.

This prevents semaphore exhaustion (max 5 concurrent tasks) and session
deadlocks when an agent execution hangs without crashing.

## Bot-Authored Ingress Guard (bot 互刷与告警噪音防护)

Co-resident bots (alert feeds, sign-in bots, other AI agents) share group
chats with humans. Unchecked, they burn LLM turns on free-response groups and
two automation agents replying to each other can loop forever. Defense in
depth, mirroring Hermes v0.20.5 semantics:

1. **Sender gate (layer 0)** — `should_respond_in_group_support`
   (policy_resolver_support.py): a bot-authored message never triggers a turn
   unless it explicitly addresses this bot (`msg.mentioned`). Runs before
   free-response whitelist / mute / thread exemption / PREFIX-ALL layers.
2. **Implicit-mention hygiene (providers)** — reply-to-bot (Telegram) and
   thread auto-reply (Slack) grant implicit mention **only to human senders**;
   a bot replying to our message must not wake the agent. `is_bot` is
   collected on Telegram/Feishu/Discord/Slack (`bot_id`).
3. **BotLoopGuard (loop backstop)** — admitted bot triggers (explicit
   mentions, DM relays) are counted per conversation; 20 events within 300s
   trip a 600s cooldown. Built-in safety default, no config surface; humans
   are never counted nor dropped.
4. **Observed-context hygiene** — bot chatter never enters the
   `GroupContextBuffer` (memory path: `msg.is_bot`), and context retrieval
   (repo `get_recent_context`) excludes agent self rows (session transcript
   already carries them) plus bot/alert sender names (`is_alert_or_bot_sender`,
   same predicate as distillation).
5. **Anti-injection declaration** — `_format_group_context_section`
   (channel_bridge/agent_executor/helpers.py) anchors a fixed English
   statement under the context header: observed messages are not necessarily
   addressed to the agent; only the post-separator trigger line is a directed
   request.

Pinned by `tests/channels/routing/test_bot_loop_guard.py`,
`tests/channels/test_routing_policy_resolver.py::TestBotSenderGate`,
`tests/channels/providers/telegram/test_telegram_inbound_mention.py::TestReplyToBotImplicitMention`,
`tests/channels/providers/slack/test_slack_thread_auto_reply.py::TestBotSenderThreadGate`,
`tests/channels/test_channel_data_plane.py::TestObservedContextHygiene`, and
`tests/core/channel_bridge/test_group_context_declaration.py`.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Inbound message processing pipeline: routing, commands, policy, sessions. | — |
| bot_loop_guard.py | Core | BotLoopGuard: per-conversation sliding-window budget for bot-authored triggers (20 events/300s → 600s cooldown). Caps bot-to-bot reply loops that survive the explicit-mention gate; human messages never counted. | [OK] |
| command_defs.py | Core | CommandDef data model, CommandAction/CommandKind enums, built-in SYSTEM_COMMANDS tuple (stop, new, compact, retry, undo, yolo, personality, bind, unbind, topic, goal, steer, queue, background, kanban, memory, learn, memo, review-week, handoff, status, quota, help). | — |
| command_registry.py | Core | CommandRegistry: central O(1) lookup for slash commands. Validates names and prevents system command overwriting. | — |
| commands/（子包） | Core | 命令域子包：`commands.py`（参数解析 + 高层 handler）、`router_commands.py`（聚合 `RouterCommandsMixin`）、`router_commands_approval.py`（`/stop`、reaction/button approval）、`router_commands_session.py`（`/new`、`/compact`、`/retry`、`/undo`、topic）、`router_commands_modes.py`（`/yolo`、`/personality`、`/steer`、`/queue`）、`router_commands_goals.py`（`/goal`、`/subgoal`、`/background`、`/handoff`）、`router_commands_memory.py`（`/status`、`/kanban`、`/learn`、`/memory`）、`router_commands_quota.py`（`/quota` 直出诊断与进度倒计时）。`commands/__init__.py` 为聚合门面 | [OK] |
| context_buffer.py | Core | GroupContextBuffer: 结合持久化数据平面异步拉取与内存兜底的上下文缓冲。 | [OK] |
| graceful_degradation.py | Core | Graceful degradation controller for smooth quality adaptation. | [OK] |
| message_effects.py | Core | Message side-effect operations (typing/keepalive, reactions, placeholder, reply, busy ack). `edit_placeholder` prepares the reply like any outbound (downgrade + risk gate), edits text only and sends attachments as a files-only follow-up through the bus. send_quota_exceeded_reply 提供配额超限多语言提醒。 | [OK] |
| placeholder_strategy.py | Core | Adaptive placeholder defer (180ms) and short-circuit for fast replies; eager materialize on stream activity. | [OK] |
| policy_resolver.py | Core | Policy resolution module extracted from Router core routing logic. 支持群聊发言人特权解耦 (Group Ingress Sender-Scoped RBAC & Confused Deputy Mitigation)，仲裁 Admin (沙箱所有者特权) / Member (每日配额与受限栅栏) / Guest (元工具特权剥离)。放行 /status, /quota, /help 只读自查诊断命令。Bot-authored 入口防护：群触发与 DM 路径均经 BotLoopGuard 限流，bot 消息不进入观察上下文缓冲。 | [OK] |
| policy_resolver_support.py | 辅助 | BoundedCooldownMap + GroupFollowUpTracker + 群聊发言人身份仲裁与诊断命令判定 (resolve_group_sender_identity, is_exempt_diagnostic_command, should_respond_in_group_support)，以及沙箱所有者的唯一判定规则 `is_admin_sender`（控制面转发或 ADMIN 配对）。触发判定第 0 层为 bot 发送者门控：bot 消息仅显式 mention 可触发，防告警/互刷烧 LLM；失控循环由 BotLoopGuard 兜底。 | [OK] |
| retry_policy.py | Core | Generic retry policy component with exponential backoff, circuit breaker integration, | — |
| router.py | Core | Core inbound message routing loop. After approval/reaction/slash filtering, checks active task `busy_input_mode` (steer/redirect auto-dispatch), applies inbound risk gate (symmetric with outbound risk gate in bus.py), dispatches cron event triggers via `inbound_event_dispatch` then submits to SessionGate. | [OK] |
| router_constants.py | Core | Constants and pure helpers shared by routing modules. Includes silence reassurance thresholds and `_is_silent_content` outbound filter. Unit tests can import directly. | — |
| router_execution.py | Core | `RouterExecutionMixin` is composed into `AgentRouter` via multiple inheritance; `_prepare_execution_context` rejects search-track `route_agent_id` (external CLI aliases like `claude` unchanged); `_deliver_agent_result` auto-attaches WebUI handoff deep link button for IM channel replies and intercepts the whole outbound reply (attachments and buttons included) as a draft ApprovalRecord when `topic_ctx.reply_mode == "draft_review"` (Channel Outbound HITL); if the draft cannot be created the reply is withheld (fail-closed), never sent unreviewed. | — |
| router_host.py | Core | Typing protocols: host instance attributes required by Router Mixins. | [OK] |
| router_keys.py | Core | ``routing_session_key`` builds ``f"{channel}:{peer_id}"``; ``routing_enclave_key`` builds 4-tuple enclave ``tenant_id:channel:peer_id:agent_profile_id`` for multi-tenant and multi-agent context isolation. | [OK] |
| router_models.py | Core | Data models referenced by AgentRouter in router.py and commands/ (_ActiveTask with steering_token, `requester_id` for reaction approval auth, `locale` for stuck watchdog i18n, ReactionPolicy, etc.) | — |
| router_stream.py | Core | RouterStreamMixin composed into AgentRouter (router.py) via multiple inheritance; includes edit-in-place heartbeat loop for long-task silence detection (sends once, then edits the same message with elapsed time). `hold_reply` keeps streamed reply text out of the chat while a human still has to approve it. | — |
| router_stream_scrubber.py | Core | Stream content and progress scrubbing utilities: filters `<think>` tags and normalizes raw tool executions into user-friendly Stage descriptions. | [OK] |
| router_stream_throttle.py | Core | Pure time-interval checks for placeholder progress edits during execute_stream. | [OK] |
| channel_data_plane.py | Core | ChannelDataPlaneService: 渠道入站脱敏持久化、上下文拉取（排除 agent 自产回复与 bot/告警噪音行）、知识提取自适应打标（paired_member 与 guest 统一隔离防长期记忆投毒）与自产回复追溯。 | [OK] |
| identity_scope.py | Core | Team-shared identity resolution: TopicContext + InboundMessage → harness TeamIdentitySpec + `ident:<id>` memory namespace + credential track. Pure, no DB/LLM. | [OK] |
| follow_up.py | Core | Proactive follow-up decisions: completion receipts (message-id keyed dedup), lazy stall scan (no daemon; heartbeat-driven for silent groups), muted-set (mute survives inbound), cooldown caps. Pure predicates + best-effort send orchestration. | [OK] |
| session_gate.py | Core | Sits between Router's consume loop and the per-message handler. Supports optional `on_busy_ack` callback (30s debounce) for immediate user feedback when messages are queued or dropped. | [OK] |
| session_rate_limiter.py | Core | Session-level rate limiting for single-instance self-protection. | [OK] |
| stream_config.py | Config | Unified configuration for streaming components. | [OK] |
| stream_manager.py | Core | Streaming optimization components used by Router for intelligent updates. | [OK] |
| stream_metrics.py | Core | Provides observability into streaming quality via tracing infrastructure. | [OK] |

## Channel agent bind (`/bind`)

`/bind` persists via `SqlTopicManager.bind_topic` (SSOT). Search-track agents (`prompt_mode=search`) are rejected with `topic_search_agent_rejected` i18n — same rule as Settings channel routing API. Legacy Search binds are purged at `resolve_topic` / `get_all_topics` read time. Team identity: `/bind agent=X identity=NAME identity_scope=shared|private|inherit` attaches a named shared identity (stable id, display-only name); revocation freezes routing to the default agent while retaining stored memory.

## Key Dependencies

- `infra`
- `utils`
