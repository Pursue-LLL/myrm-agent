# app/channels/delegation/

## Overview
Asynchronous delegation of long-running chat requests: a `/delegate` (or detected long-task) message runs in the background while the chat stays free, in-flight messages steer the running task, and the outcome is delivered back to the originating chat. Manages delegated task lifecycles and steering tokens.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package Root | Subsystem initialization. | ✅ |
| `delegation_models.py` | Models | `DelegationStatus` (pending / running / completed / failed / timed_out / cancelled) and `DelegationTask` (origin, `prompt`, status, timestamps, error text, time limit). | ✅ |
| `delegation_coordinator.py` | Core | Central coordinator managing task state machines, steering, watchdog reaping, and background execution lifecycle. The task result is the last `OutboundMessage` of the (cumulative) stream; a reply marked as a failed turn finishes the task as FAILED with its member-safe text, an exception finishes it as FAILED with the same wording (raw error only in the log), and a task the reaper already marked `TIMED_OUT` keeps that status when its cancelled stream ends. The outcome is delivered through `build_delivery_message`, except when the stream stopped at a tool approval (a `ProgressUpdate` carrying quick replies): that run has not finished, so the lifecycle hands the approval prompt to the chat through the `hand_over_approval` callback (the router registers it as a pending approval) and delivers nothing; the approval's own reply or timeout reports what happened. Each running task keeps its asyncio runner next to its tokens. Tasks are found by channel, chat and user (`find_active_task`, `running_task_ids`), so steering and `/stop` stay inside the chat a task was delegated from and a group member never reaches another member's task; the owner is `msg.user_id or msg.sender_id`, the identity the router uses everywhere. The stream is consumed inside `delegated_run_heartbeat`, which ends before an approval is handed over. `cancel_for_chat` (the user's `/stop`) and `reap_stale_tasks` (the time limit) both cancel the token and the runner together, with no grace period, so a hung run is stopped for real: `/stop` marks the task `CANCELLED` and says nothing more (the router already confirmed), the reaper marks it `TIMED_OUT` and delivers the timeout notice. Either way the task leaves the per-user quota. Tasks live in memory only; a restart ends them. Once the outcome is handled the coordinator forgets the task, its tokens and its runner. | ✅ |
| `delegation_heartbeat.py` | Heartbeat | `delegated_run_heartbeat`: an async context manager that, for the duration of the run, edits one "still running" message in the origin chat (`delegation_still_running` in `i18n/locales`: task id, elapsed minutes, steps, stage) through the shared `run_reassurance_loop`. The run's progress is invisible to the chat, so the heartbeat is time-triggered (every `HEARTBEAT_INTERVAL_SECONDS`, 5 minutes; at most `timeout_seconds // interval` of them), not silence-gated; a channel that cannot edit gets the first heartbeat only. It ends with the block: run finished, stopped, or stopped at an approval. | ✅ |
| `delegation_ingress.py` | Ingress | Channel message parsing, delegation trigger extraction, and the per-user concurrency guard. The four acknowledgements of the `/delegate` flow (task missing, quota reached, receipt, steering injected) are built by `routing/commands/router_commands_delegation.py` (and the `/delegate` steering branch of `routing/router.py`) from the channel catalog (`delegation_*` in `i18n/locales`) in the sender's locale. | ✅ |
| `delegation_delivery.py` | Delivery | `build_delivery_message`: the delivered message is the executor's own final reply (text, attachments, thread) under a one-line localized header (`delegation_done` / `delegation_failed` / `delegation_timed_out`, `delegation_duration_*`, `delegation_no_output` in `i18n/locales`); a failed task delivers its member-safe text, a timed-out task only the notice; without a final reply the message is built with `CorrelationContext.create_reply`. | ✅ |


## Key Dependencies

- `app.channels` (underlying channel transports)
- `app.channels.i18n` (delivery header and notices in the sender's locale)
- `app.channels.routing.friendly_errors` (member-safe failure text)
- `app.channels.routing.router_reassurance`, `app.channels.routing.router_stream_scrubber` (heartbeat loop and progress stage labels)
- `myrm_agent_harness.utils.runtime.steering` (steering tokens)
- `myrm_agent_harness.utils.runtime.cancellation` (cancellation tokens)
