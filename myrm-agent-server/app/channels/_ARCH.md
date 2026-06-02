# channels/

## Overview
Multi-platform messaging channel framework. Provides channel abstractions, message bus, gateway, provider implementations (Feishu/Slack/Discord/Telegram/WhatsApp/WeChat/DingTalk/Matrix/QQ/Mattermost/Line etc.), inbound routing, outbound rendering, and reliability infrastructure.

Business-layer adaptation (pairing, agent binding, config loading) lives in `app/core/channel_bridge/`.

Detailed design: [CHANNELS_SYSTEM.md](CHANNELS_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Channels toolkit entry point. Aggregates channel abstractions, message bus, gateway, | ✅ |

| Submodule | Description |
|-----------|-------------|
| core/ | Core infrastructure: BaseChannel, MessageBus, ChannelGateway, EventEmitter, Credentials, Mixins. |
| helpers/ | Helper classes for channel functionality. |
| i18n/ | Channel slash-command static message catalogs (en / zh-CN) and locale helpers. |
| implementations/ | Implementation layer for web framework integration. Provides out-of-the-box |
| media/ | Media download system with streaming, validation, retry, cache, and sticker vision. |
| protocols/ | Channel system protocols — interfaces for business-layer injection. |
| providers/ | Channel providers — concrete channel implementations. |
| reliability/ | Transmission reliability: rate limiting, concurrency control, and reconnect. |
| rendering/ | Outbound message formatting: Markdown/plaintext rendering and message splitting. |
| routing/ | Inbound message processing pipeline: routing, commands, policy, sessions. |
| security/ | Webhook security layer. Defines inbound security protocols (signature verification, |
| storage/ | Framework layer storage module. Provides out-of-the-box storage implementations |
| testing/ | Testing utilities for channel route registration. |
| types/ | Channel system domain types — pure data definitions, no I/O. |
| voice/ | Voice subsystem: STT transcription, TTS synthesis, and voice message routing. |
