# agent/streaming/recovery/

## Overview
Streaming error-recovery strategies. **`stream_recovery.py`** composes the recovery mixins consumed by `stream_executor.py` via multiple inheritance.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports the four recovery mixins | ✅ |
| context_pressure_gate.py | Gate | Pre-flight context pressure gate, token budget compaction, and presumed-overflow recovery handler (a 400 that states the model's own output ceiling is never presumed to be an overflow) | ✅ |
| goal_session.py | Core | `goal_session_id(ctx)`: the goal lookup key of a run (chat id, else session id, else message id); shared by goal continuation and provider-window parking so both address the same goal | ✅ |
| stream_recovery.py | Core | StreamRecoveryMixin — composes overflow, LLM failover (with fast-failover on is_quota_exhausted), safety refusal fallback, transient retry (short-circuited on quota exhaustion), and the mixins that hold the other strategies (turn-end, truncation, one-shot, provider-window, continuation) | ✅ |
| stream_recovery_turn_end.py | Core | StreamTurnEndRecoveryMixin — what runs on the messages of a turn that finished badly: iteration-limit handling with a toolless grace-call summary (the history goes out without its signed reasoning blocks, since the grace prompt is not the conversation's), and empty-response recovery (re-runs through `_redrive_with_hint`) | ✅ |
| stream_recovery_redrive.py | Core | StreamRedriveMixin — `_redrive_with_messages(carried, appended)`: the one way a turn is run again with messages appended (truncation and empty-response recoveries through `_redrive_with_hint`, steering directly). A fresh turn is rebuilt from `carried` plus `appended`; a resumed turn continues from its thread, so `carried` holds only what the thread lacks | ✅ |
| stream_recovery_budget.py | Core | StreamOutputBudgetMixin — output-budget half of truncation recovery, inherited by `StreamTruncationRecoveryMixin`: `_boost_output_tokens` sets the one-shot larger budget a retry runs with (2x/3x/4x of the base, capped at `MAX_EPHEMERAL_OUTPUT_TOKENS` and at the model's documented output ceiling; a base that already reaches a cap or ceiling is kept as is), starting from the configured `max_tokens` or, failing that, a thinking model's headroom floor | ✅ |
| stream_recovery_continuation.py | Core | StreamContinuationRecoveryMixin — steering/redirect injection on fresh and resumed turns, the turn's last steering gate (`_close_steering`), subagent completion, goal continuation | ✅ |
| stream_recovery_oneshot.py | Core | OneshotRecoveryMixin — targeted one-shot recovery (THINKING_SIGNATURE / REASONING_MANDATORY / DUPLICATE_TOOL_USE_ID / IMAGE_TOO_LARGE / MEDIA_REJECTED / ALLOWED_TOOLS_TOOL_CHOICE_REJECTED / LONG_CONTEXT_TIER); image surgery delegates to `stream_recovery_image_shrink` | ✅ |
| stream_recovery_image_shrink.py | Core | Provider image-limit recovery primitives: `parse_image_max_dimension` reads the ceiling the provider states (default 8000), `shrink_oversized_images` re-compresses each over-limit base64 image against both the base64 byte ceiling and the pixel ceiling (a pixel-correct downscale is accepted even when its bytes grew, a byte-triggered shrink that did not shrink is refused), and falls back to `evict_aggregate_historical_images` — older images degraded to 512px WebP or replaced by a semantic placeholder while the latest turn is protected — when no single image is oversized but the aggregate payload is | ✅ |
| stream_recovery_window.py | Core | ProviderWindowRecoveryMixin — `_handle_provider_window` for RATE_LIMIT / BILLING / OVERLOADED errors after model failover and before blind transient backoff: reads the provider-stated retry boundary once (`extract_provider_window`), then serves a ≤300 s wait exactly in-turn (`WindowAction.RETRY`), parks the running goal until the reset (`park_goal_for_provider_window`, `WindowAction.HELD`), or ends the turn at once with the real reset time (`WindowAction.FAIL`; `cooldown_remaining_ms` rides the error context). Also owns the cancel-aware sleep shared with transient retry | ✅ |
| turn_retry_state.py | Core | `TurnRetryState` — per-attempt one-shot recovery guards (format/payload, reasoning effort, PAAS 1305) and restart signals, bound fresh to StreamContext per API attempt so a guard fires at most once and prompt cache keys survive | — |
| stream_recovery_truncation.py | Core | StreamTruncationRecoveryMixin — length/max-token continuation, retry of truncated or withheld tool calls (one retry with a larger output budget from `StreamOutputBudgetMixin`), reasoning-only retry with a raised budget, and a log line per withheld call (`describe_withheld_tool_calls`); every retry re-runs through `StreamRedriveMixin`; `reset_ephemeral_max_output_tokens` | ✅ |

## Invariants

- **Tag-wrapped reasoning is not content.** Providers that inline the thinking phase into
  `content` (MiniMax emits `<think>…</think>`) look like they produced user-visible text.
  `_has_inline_reasoning` strips `THINKING_TAG_NAMES` blocks before the content probe, so a
  reasoning-only reply routes to recovery instead of being mistaken for an answer — the
  stream layer already strips those tags, meaning the user saw an empty turn.
- **A withheld tool call is a tool call.** Arguments that are cut off or unparseable are never
  executed: the adapter records them in `additional_kwargs["tool_call_recovery"]` (`safe=False`)
  and emits no `tool_calls`, so LangGraph ends the turn on a message with nothing else in it.
  `event_handlers` therefore keeps such a message in `collected_messages`, the length-truncation
  handler fires on it whatever `finish_reason` the provider reported, and
  `_has_tool_calls` — the one predicate shared by the truncation and empty-response handlers — counts
  it, so the turn is retried once or reported (`tool_call_truncated`); it never ends silently or
  is mistaken for an empty reply. The retry re-sends the original request plus one appended hint
  (a resumed turn sends the hint alone, see below) and a one-shot larger `max_tokens`; the prompt prefix is
  untouched, so the provider cache hits.
- **An output ceiling is not an overflow.** A 400 stating the model's own `max_tokens` ceiling has
  nothing to do with context size. The adapter loop (`adapters/chat_model/output_cap_recovery.py`)
  lowers `max_tokens` and retries; when it declines, `is_presumed_overflow` declines too (it reads the
  same wording through `errors.output_limit.parse_output_limit`), so a high-occupancy session is not
  compacted — a destructive step that cannot cure the error — and the original error surfaces.
- **A resumed turn re-runs from its thread.** After an approval `agent_input` is a `Command` that
  LangGraph has already consumed. Replaying one is a no-op once the graph has run to its end (verified:
  zero stream chunks), which is exactly when the truncation and empty-response recoveries fire. Those
  recoveries therefore re-run through
  `_redrive_with_hint`: a fresh turn's input is rebuilt from its collected messages plus the hint, a
  resumed turn's is `{"messages": [hint]}`, which continues from the checkpoint and leaves the prefix the
  provider caches untouched. Steering takes the same road (`_redrive_with_messages`): on a resumed turn
  the continue-mode input holds the steer, plus the one reply a redirect cut, which the graph never
  committed to the thread. The failed reply stays in the thread and `dangling_tool_call_middleware`
  answers a withheld call with an invalid-arguments result, so the model reads what failed before it reads
  the hint. A retried write asks for approval again, as any new call does. Failover and transient
  retry act while the stream is still mid-run and replay the `Command` itself (verified for 429, 500 and 503
  after an approval); overflow compaction, goal continuation and the one-shot
  recoveries are declined on a resumed turn.
- **A steer the run accepted is delivered or was never accepted.** `SteeringToken.steer`/`redirect` return
  whether the run took the message; callers keep a refused one (the web client queues it as the next turn,
  `/steer` submits it as a turn of its own, delegation and background callers report it as not steered).
  Two things keep an accepted message from being lost: a pass restarted by error recovery keeps what the
  last pass's tools had already taken off the queue (`reset_turn` returns activated-but-uncollected messages
  to the queue), and the turn does not end until `_close_steering` has closed the token with nothing
  waiting. The close is one atomic step (`close_if_idle`), so a message that gets in after the steering
  handler looked is injected and the turn runs once more, and every later one is refused. Only a turn that
  completes closes its token: a failed attempt leaves it open because a sub-agent retries on the same token.
  Not covered: a turn that ends through a provider-window hold, the iteration limit without a goal, or a
  fatal error does not pass the gate, so a steer accepted in its last moments is not read.
- **Recovery hints are runtime-authored.** The hint a recovery appends is a
  HumanMessage built by `runtime_human_message`, marked `is_system_synthetic`: the approval intent ledger
  and the user-input guard read user words and skip it. Steering is the user's own message and stays
  unmarked.
- **The recovery handlers judge the run's latest reply, not the last one in `collected_messages`.**
  `event_handlers` leaves an AIMessage with no content, no tool calls and no withheld calls out of
  `collected_messages` (there is nothing to re-send), so a handler that scanned it for the last AIMessage judged
  an earlier round's reply: an empty reply after a tool round ended the run with no answer, a reasoning-only reply
  cut by the output limit was retried as a failed tool call, and an empty first reply had no earlier reply to be
  mistaken for and was ignored. `StreamDispatcherMixin` therefore records `_latest_reply` from every `updates`
  chunk (`latest_reply.latest_model_reply`); `StreamExecutor` clears it at the start of each pass, so a pass that
  delivers no reply recovers nothing. `collected_messages` stays what a retry carries (a tool-call retry and a
  thinking-budget retry leave the failed reply out of it by identity). The reply itself stays in the thread, as it
  does when a turn simply ends on it.
- **A length cut inside the reasoning belongs to the truncation recovery alone.** Once the thinking-budget
  recovery has raised the budget as far as it goes and gives up, `_handle_empty_response` stands down for that
  reply (`_cut_by_output_limit`): another attempt at the base budget would be cut again. Replies that
  stopped normally with nothing but reasoning, or with nothing at all, are empty responses: two retries, then a
  `MyrmLLMError(FORMAT_ERROR)`.
- **Budget boost needs a real base.** `_boost_output_tokens` scales from the configured
  `max_tokens`; with none configured it falls back to `thinking_output_floor` for known thinking
  models and stays a safe no-op otherwise (an unknown ceiling could otherwise be overshot). The scaled
  budget is also bounded by the model's documented output ceiling (`clamp_budget_to_model_ceiling`), so a
  retry cannot turn a truncated answer into a provider 400; a ceiling below the base is a stale table
  entry — the base was already served — and is ignored.

- **Retry timing follows the provider-stated boundary.** When the provider says when the window reopens,
  `_handle_provider_window` is the only retry policy: a short wait is slept exactly (cancel-aware), a
  longer one parks the goal as `WAIT` (`wait_kind=usage_limit`, `wait_resume_at`) and ends the turn, and a
  boundary beyond the 24 h hold cap or a spent quota with no boundary fails at once. Blind transient
  backoff only runs when the provider gave no signal. A goal that held without completing a turn in
  between is paused after `MAX_NO_PROGRESS_HOLDS`, so a provider that keeps rejecting cannot loop forever.

## Key Dependencies

- `agent._internals.agent_recovery`
- `agent.errors.fault_side`
- `agent.config.llm_safety` (grace call re-pairs its history through `normalize_messages`)
- `toolkits.llms.errors.classifier`
