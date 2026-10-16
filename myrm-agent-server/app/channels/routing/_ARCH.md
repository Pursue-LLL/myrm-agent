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
   records are updated; for an already-resolved approval (duplicate click, TTL
   sweep) the card is edited to the localized `approval_already_resolved` line
   and the handler exits (prevents status flip on duplicate button clicks).
4. **Edits** the original IM message to the localized status line
   (`approval_resolved_approved` / `approval_resolved_denied`, e.g. "Approved by
   @user") so stale buttons stop inviting clicks.
5. **Routes by type** — a held reply (`action_type == "outbound_draft"`) ends at
   step 4: `resolve_approval` has already sent or released it (see *Held Replies*),
   and no LangGraph resume is needed. Otherwise, **resumes** the interrupted
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

- built-in system commands (`CommandDef.owner_only`), in DMs and groups alike.
  Commands are dispatched before `PolicyResolver`, before any identity or fence
  exists, and they act on the owner's sandbox (memory, kanban, topic bindings,
  background runs), so a system command is owner-only unless it opts in with
  `any_sender=True`. The opt-in set is the commands confined to the sender's own
  conversation that cost at most one turn: `/stop /new /compact /retry /undo
  /personality /steer /queue /status /quota /help`. Skill and agent commands are
  never owner-only: they go through the per-turn pipeline, which resolves identity
  and applies the untrusted-ingress fence. `/help` lists only what the sender may run;
- mobile task delegation and in-flight steering of a delegated run: both execute
  outside the per-turn pipeline, so anyone else's message continues as an ordinary
  turn;
- decisions on held replies: the button path above, and `/draft` (an owner-only system command).

The check sees the raw `msg.sender_id`.

## Event-Trigger Admission

A cron event trigger starts an unattended job on the owner's account, so it follows the same sender policy and the same
tool fence as a chat turn from that sender. The resolvers that enforce them (`resolve_dm_user`, `resolve_group_user`)
run after the trigger hook and have side effects (inbound ledger, context buffer, pending pairings, LID binding, quota
replies, loop-guard budget), so the router first asks `PolicyResolver` two read-only questions
(`sender_admission.py`, both change nothing): `is_sender_admitted` (mirrors the admission rules: may this sender start
a job) and `is_untrusted_event_sender` (is this sender anyone but the owner). `AgentRouter._is_sender_admitted` and
`_is_untrusted_event_sender` fail closed (a lookup error skips the trigger, respectively fences the job, and logs a
warning, because the consume loop has no per-message guard).

- Admitted: control-plane forwards (they carry an identity the control plane already resolved,
  `api/channels/channel_ingress.py`), the owner, DM senders the DM policy lets in (OPEN, an ACTIVE pairing — a
  WhatsApp LID counts through its verified phone mapping, without being bound — or an identity the adapter already
  resolved), and group messages from enabled groups or from guests when guest mention mode allows them.
- Dropped: whatever the resolvers would ignore — strangers under ALLOWLIST/PAIRING, blocked or pending pairings,
  DISABLED policies, messages from groups that are not enabled.
- Group admission is per chat, not per mention: an unaddressed message in an enabled group still fires a trigger, so a
  group can be watched quietly while the bot only answers when mentioned.
- Not applied, on purpose: the member quota and `BotLoopGuard`; both cap chat turns, not trigger matching.
- Not checked: `POST /cron/trigger/event` under the API prefix (`api/cron/routes/triggers.py`), an authenticated REST
  call that carries no sender.
- Fenced, for anyone but the owner: a job the trigger starts for a paired member, a guest or any sender without an
  ACTIVE admin pairing runs under the tool fence of an untrusted chat turn. Only an ACTIVE admin pairing resolves to the
  owner's identity, so that is the pairing `is_untrusted_event_sender` looks for; a control-plane forward passes the
  admin check whatever identity it carries, so the identity it arrives with is tested as well (`is_untrusted_sender`).
  `inbound_event_dispatch.py` opens the harness `untrusted_ingress_scope()` around `CronScheduler.dispatch_event`; the
  job tasks the scheduler spawns inherit it, and `core/cron/adapters/agent_runner.py` reads it. For such a run the
  read-only research lease is forced (`research_lease.py`), memory is off, the job is never queued as a goal in a chat
  and the MAIN chat history is not loaded, and workflow-template jobs are skipped. The matched message text is still
  appended to the job prompt after the injection scan; for a non-owner sender the lease bounds what it can steer.
- Not fenced: the owner's own messages, and the other trigger sources (schedule, manual run, REST, webhook, system
  event).

The verdict and the resolvers read the same LID-to-phone mapping (`lid_mapped_phone` in `policy_resolver_support.py`);
only the resolvers go on to bind it. `tests/channels/routing/test_sender_admission.py` runs both verdicts and the real
resolvers over the same matrix of DM policy, pairing status, group state and guest mention: admission is compared with
whether the resolver lets the sender in, and trust with whether the identity the resolver gives the chat turn is fenced
by `is_untrusted_sender`, so a rule changed on one side only fails there.

## Held Replies (`reply_mode=draft_review`)

`TopicContext.holds_reply_for_review` is the single predicate for every stage
that could expose a reply before a human approved it. While it holds,
`_consume_executor_stream(hold_reply=True)` never edits streamed text into the
placeholder (progress updates still show) — resumed turns included, which is why
the flag is separate from `topic_context` — and `_deliver_agent_result` turns the
final reply into an `outbound_draft` approval; nothing is sent until the owner approves it.

The sender is left with the placeholder edited to `draft_review_pending`; its id is stored
in the draft (`payload.placeholder_id`). Whoever decides on the draft — WebUI, the button
path above, batch approve or the TTL sweeper — goes through `ApprovalRegistry`, which calls
`services/approvals/outbound_draft.py::finalize_outbound_draft`: it sends the approved
reply or releases the rejected/expired one, closes that placeholder (the same edit-then-delete
cleanup the router uses, `MessageEffects.cleanup_placeholder`), and tells the owner when an
approved reply could not go out. The router itself never sends or releases a held reply.

Where the owner's review request carries no buttons (every channel but Telegram), it ends with the commands
that decide it from chat: `/draft approve <code>` and `/draft reject <code>`
(`commands/router_commands_draft.py`). The code is the first 8 characters of the approval id
(`outbound_draft.draft_code`); a command accepts 6 or more hex characters.
`ApprovalRegistry.find_pending_outbound_drafts` resolves it among pending held replies only, so a draft code
can never decide any other approval, and a code that fits two replies decides neither. The decision then goes
through the same `resolve_approval` funnel as every other door.

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
| command_defs.py | Core | CommandDef data model (`any_sender` opt-in + `owner_only` property: system commands are owner-only unless confined to the sender's own conversation), CommandAction/CommandKind enums, built-in SYSTEM_COMMANDS tuple (stop, new, compact, retry, undo, yolo, personality, bind, unbind, topic, draft, goal, subgoal, steer, queue, background, btw, handoff, kanban, memory, learn, memo, review-week, design-image, status, quota, help). | — |
| command_registry.py | Core | CommandRegistry: central O(1) lookup for slash commands. Validates names and prevents system command overwriting. `help_lines(owner=…)` leaves owner-only commands out for other senders. | — |
| commands/（子包） | Core | 命令域子包：`commands.py`（参数解析 + 高层 handler）、`router_commands.py`（聚合 `RouterCommandsMixin`）、`router_commands_approval.py`（`/stop`、reaction/button approval）、`router_commands_session.py`（`/new`、`/compact`、`/retry`、`/undo`、topic）、`router_commands_modes.py`（`/yolo`、`/personality`、`/steer`、`/queue`）、`router_commands_goals.py`（`/goal`、`/subgoal`、`/background`、`/handoff`）、`router_commands_memory.py`（`/status`、`/kanban`、`/learn`、`/memory`）、`router_commands_draft.py`（`/draft`：在聊天里批准或拒绝被扣留的回复）、`router_commands_quota.py`（`/quota` 直出诊断与进度倒计时）。`commands/__init__.py` 为聚合门面 | [OK] |
| context_buffer.py | Core | GroupContextBuffer: 结合持久化数据平面异步拉取与内存兜底的上下文缓冲。 | [OK] |
| friendly_errors.py | Core | Member-safe error wording: `friendly_error_text(kind)` / `friendly_error_message(exc)` return one localized sentence per `ErrorKind` plus an 8-hex reference id (operators grep the logs by it); the provider's text, endpoints and diagnostic steps never reach the chat. Billing, auth and model-not-found additionally get account guidance (`error_*_owner` keys: top up, check the key, pick another model) only when the caller passes `account_guidance=True`, which the executor does for a trusted owner's direct message and never for guests, paired members or groups. `ERROR_TYPE_METADATA_KEY` / `is_error_reply` mark a reply as a failed turn (the delegation coordinator reads the marker). Shared by the router's exception path, the executor's failed-stream and exception replies, and the delegation coordinator (exception wording and the failed-turn marker). | [OK] |
| graceful_degradation.py | Core | Graceful degradation controller for smooth quality adaptation. | [OK] |
| inbound_risk_gate.py | Core | IM wrapper of the shared risk entry `screen_user_text` (`services/risk/ingress.py`): a user-typed inbound text that matches a risk rule is held, the sender gets the fixed `risk_inbound_blocked` notice (the chat for groups, the sender for DMs) and the message never reaches an agent. Used by the router's turn, busy steer/redirect, delegation and in-flight steering paths, for every system command with arguments (`/steer`, `/background`, `/goal`, `/kanban`, …) once in `_dispatch_resolved`, and for the reason of `/deny <reason>` in `_handle_approval_command` (a held reason leaves the approval pending). | [OK] |
| message_effects.py | Core | Message side-effect operations (typing/keepalive, reactions, placeholder, reply, busy ack). `edit_placeholder` prepares the reply like any outbound (downgrade + risk gate), edits text only and sends attachments as a files-only follow-up through the bus. send_quota_exceeded_reply 提供配额超限多语言提醒。 | [OK] |
| placeholder_strategy.py | Core | Adaptive placeholder defer (180ms) and short-circuit for fast replies; eager materialize on stream activity. | [OK] |
| policy_resolver.py | Core | Inbound policy resolution: decides whether a message reaches an agent turn and under which identity. 支持群聊发言人特权解耦 (Group Ingress Sender-Scoped RBAC & Confused Deputy Mitigation)，仲裁 Admin (沙箱所有者特权) / Member (每日配额与受限栅栏) / Guest (元工具特权剥离)。放行 /status, /quota, /help 只读自查诊断命令。Bot-authored 入口防护：群触发与 DM 路径均经 BotLoopGuard 限流，bot 消息不进入观察上下文缓冲。`is_sender_admitted` / `is_untrusted_event_sender` 暴露只读准入与发送者信任判定（`sender_admission.py`），供路由器在解析器之前为 cron 事件触发把关并划定工具栅栏。 | [OK] |
| policy_resolver_support.py | 辅助 | BoundedCooldownMap + GroupFollowUpTracker + 群聊发言人身份仲裁与诊断命令判定 (resolve_group_sender_identity, is_exempt_diagnostic_command, should_respond_in_group_support)，以及沙箱所有者的唯一判定规则 `is_admin_sender`（控制面转发或 ADMIN 配对）、控制面转发判定 `is_control_plane_forward`（解析器与准入判定共用）、DM 配对查找 `resolve_paired_user`（含 WhatsApp LID 回退绑定）与只读的 LID→手机号映射 `lid_mapped_phone`。触发判定第 0 层为 bot 发送者门控：bot 消息仅显式 mention 可触发，防告警/互刷烧 LLM；失控循环由 BotLoopGuard 兜底。 | [OK] |
| retry_policy.py | Core | Generic retry policy component with exponential backoff, circuit breaker integration, | — |
| router.py | Core | Core inbound message routing loop. After approval/reaction/slash filtering, checks active task `busy_input_mode` (steer/redirect auto-dispatch), applies inbound risk gate (`hold_risky_inbound`; symmetric with outbound risk gate in bus.py) to every user-typed text before it reaches an agent (it screens `msg.content`; voice and video transcripts are merged into it and screened, while document text rides in `metadata.document_text_blocks` and images in `metadata.image_data_list`, which are not screened): the turn text in `_handle_merged` before the long-text spill, and the busy steer/redirect, delegation prompt and in-flight delegation steering paths, and the arguments of system commands in `_dispatch_resolved` (commands that act on their text directly: a background task, a goal, a kanban card, a steer; agent-route and skill commands are screened on the agent path they reach); a held turn acknowledges its inbound journal entry before returning (every early return of `_handle_merged` does, via `_acknowledge_inbound`), dispatches cron event triggers via `inbound_event_dispatch` (only for senders the access policy admits, `_is_sender_admitted`, fail-closed; the dispatch screens the text with `screen_user_text` first, so a held message starts no job; the turn path of that message records the hit and tells the sender (the dispatch only detects); the job runs under the untrusted-ingress fence when `_is_untrusted_event_sender`, fail-closed) then submits to SessionGate. | [OK] |
| router_constants.py | Core | Constants and pure helpers shared by routing modules. Includes silence reassurance thresholds and `_is_silent_content` outbound filter. Unit tests can import directly. | — |
| router_execution.py | Core | `RouterExecutionMixin` is composed into `AgentRouter` via multiple inheritance; `_prepare_execution_context` rejects search-track `route_agent_id` (external CLI aliases like `claude` unchanged); `_deliver_agent_result` auto-attaches WebUI handoff deep link button for IM channel replies and intercepts the whole outbound reply (attachments and buttons included) as a draft ApprovalRecord when `topic_ctx.reply_mode == "draft_review"` (Channel Outbound HITL); if the draft cannot be created the reply is withheld (fail-closed), never sent unreviewed. | — |
| router_host.py | Core | Typing protocols: host instance attributes required by Router Mixins. | [OK] |
| router_keys.py | Core | ``routing_session_key`` builds ``f"{channel}:{peer_id}"``; ``routing_enclave_key`` builds 4-tuple enclave ``tenant_id:channel:peer_id:agent_profile_id`` for multi-tenant and multi-agent context isolation. | [OK] |
| router_models.py | Core | Data models referenced by AgentRouter in router.py and commands/ (_ActiveTask with steering_token, `requester_id` for reaction approval auth, `locale` for stuck watchdog i18n, ReactionPolicy, etc.) | — |
| router_stream.py | Core | RouterStreamMixin composed into AgentRouter (router.py) via multiple inheritance; includes edit-in-place heartbeat loop for long-task silence detection (sends once, then edits the same message with elapsed time). `hold_reply` keeps streamed reply text out of the chat while a human still has to approve it. | — |
| router_stream_scrubber.py | Core | Stream content and progress scrubbing utilities: filters `<think>` tags and normalizes raw tool executions into user-friendly Stage descriptions. | [OK] |
| router_stream_throttle.py | Core | Pure time-interval checks for placeholder progress edits during execute_stream. | [OK] |
| channel_data_plane.py | Core | ChannelDataPlaneService: 渠道入站脱敏持久化、上下文拉取（排除 agent 自产回复与 bot/告警噪音行）、知识提取自适应打标（paired_member 与 guest 经 `is_untrusted_sender` 统一隔离防长期记忆投毒）与自产回复追溯。 | [OK] |
| identity_scope.py | Core | Team-shared identity resolution: TopicContext + InboundMessage → harness TeamIdentitySpec + `ident:<id>` memory namespace + credential track; `is_untrusted_sender` (SSOT for guest / paired-member predicate) and `resolve_turn_memory_scope` (group, guest and paired-member turns get a memory compartment: stable `ident:` namespace per group chat or per untrusted DM sender, never the owner's `global` / `agent:<id>`; conversation_search disabled; named identity bound with `inherit` shares the channel baseline compartment across its groups). `default_identity_id` keeps namespace-safe ids readable and appends a raw-id digest to any id sanitising would alter, so distinct chats never share a compartment. Pure, no DB/LLM. | [OK] |
| follow_up.py | Core | Proactive follow-up decisions: completion receipts (message-id keyed dedup), lazy stall scan (no daemon; heartbeat-driven for silent groups), muted-set (mute survives inbound), cooldown caps. Pure predicates + best-effort send orchestration. | [OK] |
| sender_admission.py | Core | `check_sender_admitted`: read-only verdict on whether the access policy would let a sender through to an agent turn. Mirrors the admission gates of `resolve_dm_user` / `resolve_group_user` (control-plane forward, group policy + enabled groups / guest @mention, DM policy + ACTIVE pairing incl. verified WhatsApp LID mapping, owner always) without their side effects (no replies, quota, pending pairing, LID binding, ledger write). `is_untrusted_event_sender`: whether the sender is anyone but the owner (an unresolved sender is judged by its ACTIVE admin pairing, a pre-resolved identity also by `is_untrusted_sender`), which decides whether a triggered job runs fenced. Both gate cron event triggers in `router.py`. | [OK] |
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
