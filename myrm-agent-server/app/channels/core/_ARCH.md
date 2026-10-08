# core/

## Overview
Core infrastructure: BaseChannel, MessageBus, ChannelGateway, EventEmitter, Credentials, Mixins.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Core infrastructure: BaseChannel, MessageBus, ChannelGateway, EventEmitter, Credentials, Mixins. | — |
| allow_policy.py | Core | Inbound access control policy. ChatPolicy, FilterReason, ChatPolicyOverride, AllowPolicy with bot_policy and per-chat overrides. | ✅ |
| base.py | Core | Channel abstraction layer. All providers inherit this class; Gateway manages them uniformly. | ✅ |
| bus.py | Core | Message routing hub and state holder: queues, channel registry, durable publish (IM channels persist via DurableOutboundGate before dispatch), inbound handoff and DLQ admin. The delivery pipeline lives in `OutboundDispatchMixin`. | ✅ |
| credentials.py | Core | Framework-level credential type definitions and generic parser. Providers declare | ✅ |
| events.py | Core | Channel event infrastructure. Channels emit events (status changes, group updates), | ✅ |
| exceptions.py | Core | Channel exception hierarchy for precise retry and error handling. | ✅ |
| factory.py | Core | Framework-level channel factory. Decouples credential resolution from channel instantiation; skips invalid credentials (`ValueError`) without stack traces. | ✅ |
| gateway.py | Core | Channel system entry point. Manages all channel lifecycles, health checks, error isolation, and inbound crash recovery via InboundJournal. `enable_channel` triggers durable outbound recovery. Accepts extra_commands for business-layer command injection and skill_command_handler for skill-bound slash commands. `update_skill_commands()` enables runtime hot-reload of SKILL-type command bindings without restart. `swap_channel()` is the single atomic instance-replacement primitive (remove old → add new → restore old on failure) shared by all credential hot-reload paths. | ✅ |
| logging_filter.py | Core | Framework-level log sanitization filter. Auto-detects and redacts sensitive data (token, password, s | ✅ |
| metrics.py | Core | Framework-level metrics data layer. Provides structured data only; | ✅ |
| mixins.py | Core | Reusable channel capability components via Mixin pattern. Allows different channels | ✅ |
| outbound_dispatch.py | Core | Delivery half of MessageBus. Priority dispatch loop, direct send returning message_id, control-plane egress routing, dispatch-idle durable recover; retains disk obligation when channel disabled/stopped/unregistered; null-send guard. | ✅ |
| outbound_failure.py | Core | Failure half of MessageBus. DLQ persistence, permanent-failure callback, notification dedup and DLQ threshold alert for failed outbound sends. | ✅ |
| outbound_gate.py | Core | Pre-publish outbound content & link liveness gate. Probes extracted URLs concurrently via fast HTTP HEAD/Range with TTL cache; enforces fail-closed HOLD on dead links for Cron/broadcast channels and soft warning on interactive chats. | ✅ |
| outbound_prepare.py | Core | Pure outbound transformations shared by every send path: correlation lineage, interactive component/media downgrade, outbound risk gate. | ✅ |
| rate_limit.py | Core | Rate limiting for inbound messages. | ✅ |
| user_resolver.py | Core | Generic user resolver protocol and cache implementation. Protocol-first framework design | ✅ |

## Key Dependencies

- `infra`
