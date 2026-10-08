# reliability/

## Overview
Transmission reliability: rate limiting, concurrency control, reconnect, and crash recovery.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Transmission reliability: rate limiting, concurrency control, reconnect, crash recovery. | — |
| inbound_journal.py | Core | Inbound Journal: WAL-style persistence for in-flight message processing. Ensures no user message is lost on crash/restart. Protocol + SQLite implementation. | ✅ |
| inbound_limiter.py | Core | Inbound rate limiting layer. Prevents DoS/DDoS attacks on webhook endpoints. | ✅ |
| inflight_limiter.py | Core | Concurrency control layer. Prevents resource exhaustion from concurrent request storms. | ✅ |
| rate_limiter.py | Core | Per-channel outbound rate limiting. Prevents platform bans due to excessive send frequency. | ✅ |
| reconnect.py | Core | Reconnect loop with exponential backoff + jitter for long-lived connections. | ✅ |
| retry.py | Core | Async retry utility with exponential backoff. Channel providers declare retry policies; media failures fall back to a localized text-only send; partial deliveries (`ChannelSendError.accepted`) are never retried or degraded; cancellation propagates. | ✅ |
| durable_outbound.py | Core | Durable outbound gate: disk persist before IM send, startup/enable/dispatch-idle recovery, inflight tracking, skip web/chat/silent; retains obligation when channel disabled/stopped/unregistered (`retains()` tells the bus whether a disk record still owns a dropped message's attachments); null-send must not ack. | ✅ |
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
                                       recover_into_bus → re-send
                                               ↓ (send failed / delivery unproven)
                                       harness DeadLetterQueue (retry or permanent-failure callback)
```

## Key Dependencies

- `infra`
