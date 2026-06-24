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

`parse_approval_command` (commands.py) recognises a unified, three-tier
approval alphabet (skin-tone modifiers and Unicode variation selectors are
normalised away by `normalize_approval_emoji`):

| Decision        | Emojis                                         | Text aliases                                |
|-----------------|------------------------------------------------|---------------------------------------------|
| `allow_once`    | 👍, ❤, ✅, 🤝, 💪                              | `/approve`, `1`, `y`/`yes`, `ok`, 同意, 好的 |
| `allow_always`  | ♾️, ⭐                                         | `/approve-always`, `/always`, `aa`, `!y`, 永远允许 |
| `deny`          | 👎, ❌, 🚫                                      | `/deny`, `2`, `n`/`no`, 拒绝, 不行         |

`_is_reaction_approval_valid` in `router_commands.py` enforces a layered gate:
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
- `deny`         → `{"type": "reject", "feedback": "..."}`

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Inbound message processing pipeline: routing, commands, policy, sessions. | — |
| command_defs.py | Core | CommandDef data model, CommandAction/CommandKind enums, built-in SYSTEM_COMMANDS tuple (stop, new, compact, retry, undo, yolo, personality, bind, unbind, topic, goal, steer, queue, background, kanban, memory, learn, handoff, status, help). | — |
| command_registry.py | Core | CommandRegistry: central O(1) lookup for slash commands. Validates names and prevents system command overwriting. | — |
| commands.py | Core | Pure argument parsers for complex commands (approval incl. emoji reactions, yolo, personality, memory, topic) and async command handlers. No business-specific route definitions. | ✅ |
| context_buffer.py | Core | Pure in-memory buffer, no I/O, no lifecycle management. | ✅ |
| graceful_degradation.py | Core | Graceful degradation controller for smooth quality adaptation. | ✅ |
| message_effects.py | Core | Message side-effect operations (typing/keepalive, reactions, placeholder, reply). Operational replies use `MessagePriority.SYSTEM` for important-mode notify. | ✅ |
| placeholder_strategy.py | Core | Adaptive placeholder defer (180ms) and short-circuit for fast replies; eager materialize on stream activity. | ✅ |
| policy_resolver.py | Core | Policy resolution module extracted from Router core routing logic. Guest mode requires `explicit_mention` metadata (entity-based only; reply-to-bot does not bypass non-enabled groups). | ✅ |
| policy_resolver_support.py | 辅助 | BoundedCooldownMap + GroupFollowUpTracker helpers for PolicyResolver. | ✅ |
| retry_policy.py | Core | Generic retry policy component with exponential backoff, circuit breaker integration, | — |
| router.py | Core | Core inbound message routing loop. Accepts extra_commands from business layer for agent routing. Connects MessageBus (inbound queue) to agent executor. | ✅ |
| router_commands.py | Core | RouterCommandsMixin composed into AgentRouter (router.py) via multiple inheritance; | — |
| router_constants.py | Core | Constants read by router.py, router_stream, and janitor/dedup logic. Includes silence reassurance thresholds. Unit tests can import directly. | — |
| router_execution.py | Core | `RouterExecutionMixin` is composed into `AgentRouter` via multiple inheritance; | — |
| router_host.py | Core | Typing protocols: host instance attributes required by Router Mixins. | ✅ |
| router_keys.py | Core | ``routing_session_key`` builds ``f"{channel}:{peer_id}"`` for DM/group peer maps | — |
| router_models.py | Core | Data models referenced by AgentRouter in router.py and router_commands (_ActiveTask with steering_token + `requester_id` for reaction approval auth, ReactionPolicy, etc.) | — |
| router_stream.py | Core | RouterStreamMixin composed into AgentRouter (router.py) via multiple inheritance; includes parallel reassurance loop for long-task silence detection. | — |
| router_stream_throttle.py | Core | Pure time-interval checks for placeholder progress edits during execute_stream. | ✅ |
| session_gate.py | Core | Sits between Router's consume loop and the per-message handler. | ✅ |
| session_rate_limiter.py | Core | Session-level rate limiting for single-instance self-protection. | ✅ |
| stream_config.py | Config | Unified configuration for streaming components. | ✅ |
| stream_manager.py | Core | Streaming optimization components used by Router for intelligent updates. | ✅ |
| stream_metrics.py | Core | Provides observability into streaming quality via tracing infrastructure. | ✅ |

## Key Dependencies

- `infra`
- `utils`
