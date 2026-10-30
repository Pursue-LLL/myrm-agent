# reliability/

## Overview
Transmission reliability: rate limiting, concurrency control, reconnect, and crash recovery.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Transmission reliability: rate limiting, concurrency control, reconnect, crash recovery. | — |
| inbound_journal.py | Core | Inbound Journal: WAL-style persistence for in-flight message processing. A crash replays the turn it interrupted and a stop replays the messages its gate held that had not started one; an entry is deleted when its turn ends, however it ends. An entry is the whole inbound message as JSON (`types/inbound_wire.py`) minus the yolo window; `restore_inbound` rebuilds it for the replay, marked with `METADATA_IS_RECOVERY` and `METADATA_RECOVERY_ENTRY_IDS` (the turn keeps those entries, and the agent is told the message is a replay; `is_replay` and `replay_entry_ids` read the marks, and a turn the gate merged from several replays names the entries of all of them), and drops, with a note in the text, an attachment whose local file is gone and has no url. A table of another column set is replaced when the journal opens. Protocol + SQLite implementation. | ✅ |
| inbound_limiter.py | Core | Inbound rate limiting layer. Prevents DoS/DDoS attacks on webhook endpoints. | ✅ |
| inflight_limiter.py | Core | Concurrency control layer. Prevents resource exhaustion from concurrent request storms. | ✅ |
| rate_limiter.py | Core | Per-channel outbound rate limiting. Prevents platform bans due to excessive send frequency. | ✅ |
| reconnect.py | Core | Reconnect loop with exponential backoff + jitter for long-lived connections. | ✅ |
| retry.py | Core | Async retry utility with exponential backoff. Channel providers declare retry policies; media failures fall back to a localized text-only send; partial deliveries (`ChannelSendError.accepted`) are never retried or degraded; raw transport failures are retried by type (`OSError`, `TimeoutError`, `httpx.ConnectError`), but not an `httpx` read, write or connect timeout; a provider that wraps the transport error raises `ChannelSendError(...) from exc`, and `ChannelSendError.retriable` then reads the cause (a request that may have reached the platform is never retried); cancellation propagates. | ✅ |
| durable_outbound.py | Core | Durable outbound gate: disk persist before IM send (a persist failure logs a WARNING and the message is sent from memory without a disk record), startup/enable/dispatch-idle recovery, inflight tracking, skip web/chat/silent; retains obligation when channel disabled/stopped/unregistered (`retains()` tells the bus whether a disk record still owns a dropped message's attachments); recovery re-injects only records whose channel can take a delivery (`OutboundPublisher.can_deliver`), so an undeliverable record stays on disk instead of spinning the idle poll; null-send must not ack; a record that cannot be decoded is quarantined in the dead-letter directory with an ERROR log (marked out of retries, so the dead-letter queue reports it once as permanently failed and never re-sends it), so the healthy ones still recover. | ✅ |
| delivery_notify_ledger.py | Core | Permanent-failure toast dedupe ledger (separate from outbound persist). | ✅ |

## Architecture: Symmetric Reliability

```
Inbound Flow:                          Outbound Flow:
User Message → InboundJournal.write    Agent Reply → MessageBus.publish_outbound
       ↓                                       ↓
Agent Processing                       DurableOutboundGate.prepare_enqueue (IM only)
       ↓                                       ↓
InboundJournal.acknowledge             Dispatch → Channel.send()
       ↓ (on crash)                            ↓ (success)
Gateway._recover_journal()             ack_delivery → done
                                               ↓ (channel disabled)
                                       retain disk obligation (no ack)
                                               ↓ (enable_channel / crash)
                                       recover_into_bus (only deliverable channels) → re-send
                                               ↓ (send failed / delivery unproven)
                                       harness DeadLetterQueue (retry or permanent-failure callback)
```

## Key Dependencies

- `infra`
