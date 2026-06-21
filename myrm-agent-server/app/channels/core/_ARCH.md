# core/

## Overview
Core infrastructure: BaseChannel, MessageBus, ChannelGateway, EventEmitter, Credentials, Mixins.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Core infrastructure: BaseChannel, MessageBus, ChannelGateway, EventEmitter, Credentials, Mixins. | — |
| allow_policy.py | Core | Inbound access control policy. ChatPolicy, FilterReason, ChatPolicyOverride, AllowPolicy with bot_policy and per-chat overrides. | ✅ |
| base.py | Core | Channel abstraction layer. All providers inherit this class; Gateway manages them uniformly. | ✅ |
| bus.py | Core | Message routing hub. Producers call publish_outbound; the bus dispatches by priority | ✅ |
| credentials.py | Core | Framework-level credential type definitions and generic parser. Providers declare | ✅ |
| events.py | Core | Channel event infrastructure. Channels emit events (status changes, group updates), | ✅ |
| exceptions.py | Core | Channel exception hierarchy for precise retry and error handling. | ✅ |
| factory.py | Core | Framework-level channel factory. Decouples credential resolution from channel instantiation; skips invalid credentials (`ValueError`) without stack traces. | ✅ |
| gateway.py | Core | Channel system entry point. Manages all channel lifecycles, health checks, error isolation, and inbound crash recovery via InboundJournal. Accepts extra_commands for business-layer command injection and skill_command_handler for skill-bound slash commands. `update_skill_commands()` enables runtime hot-reload of SKILL-type command bindings without restart. | ✅ |
| logging_filter.py | Core | Framework-level log sanitization filter. Auto-detects and redacts sensitive data (token, password, s | ✅ |
| metrics.py | Core | Framework-level metrics data layer. Provides structured data only; | ✅ |
| mixins.py | Core | Reusable channel capability components via Mixin pattern. Allows different channels | ✅ |
| rate_limit.py | Core | Rate limiting for inbound messages. | ✅ |
| user_resolver.py | Core | Generic user resolver protocol and cache implementation. Protocol-first framework design | ✅ |

## Key Dependencies

- `infra`
