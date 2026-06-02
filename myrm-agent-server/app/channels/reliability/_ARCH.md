# reliability/

## Overview
Transmission reliability: rate limiting, concurrency control, reconnect, and crash recovery.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Transmission reliability: rate limiting, concurrency control, reconnect, crash recovery. | — |
| dlq.py | Core | Outbound DLQ: persistent storage for messages that failed to send after all retries. | ✅ |
| inbound_journal.py | Core | Inbound Journal: WAL-style persistence for in-flight message processing. Ensures no user message is lost on crash/restart. Protocol + SQLite implementation. | ✅ |
| inbound_limiter.py | Core | Inbound rate limiting layer. Prevents DoS/DDoS attacks on webhook endpoints. | ✅ |
| inflight_limiter.py | Core | Concurrency control layer. Prevents resource exhaustion from concurrent request storms. | ✅ |
| rate_limiter.py | Core | Per-channel outbound rate limiting. Prevents platform bans due to excessive send frequency. | ✅ |
| reconnect.py | Core | Reconnect loop with exponential backoff + jitter for long-lived connections. | ✅ |
| retry.py | Core | Async retry utility with exponential backoff. Channel providers declare retry policies; | ✅ |

## Architecture: Symmetric Reliability

```
Inbound Flow:                          Outbound Flow:
User Message → InboundJournal.write    Agent Reply → MessageBus → DeliveryQueue
       ↓                                       ↓
Agent Processing                       Channel.send()
       ↓                                       ↓
InboundJournal.acknowledge             Success → done
       ↓ (on crash)                            ↓ (on failure)
Gateway._recover_journal()             DLQ.save() → AutoRetryWorker
```

## Key Dependencies

- `infra`
