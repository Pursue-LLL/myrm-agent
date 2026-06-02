# discord/

## Overview
Discord channel provider. Supports Gateway (WebSocket) and REST modes.
Handles inbound media attachments (image/video/audio/document) and
outbound rich messages (embeds, buttons, select menus, file uploads).
Forum channels (type 15) are supported: outbound messages to a Forum
channel auto-create a thread post with the content as starter message,
handling require_tag constraints. Inbound Forum thread messages inherit
the parent Forum's topic via metadata.

Voice channel support enables the bot to join Discord voice channels,
capture speech via RTP decryption, transcribe with STT, and respond
with TTS audio playback. Follow-user mode automatically tracks
configured users across voice channels with multi-user handoff,
allowed-channel enforcement, and bounded reconciliation.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Discord channel provider. | — |
| channel.py | Core | Discord channel implementation. Inbound media extraction + outbound send (with Forum auto-thread) + voice integration. | ✅ |
| config.py | Config | Discord channel configuration (gateway, voice, allowed users/guilds, follow-users, allowed-channels). | ✅ |
| helpers.py | Core | Pure-function helpers: embed/component/file builders for outbound messages. | ✅ |
| voice/ | Submodule | Discord voice channel support (RTP receive, playback, lifecycle). | ✅ |
| voice/receiver.py | Core | Multi-mode RTP decryption (AEAD/SecretBox) + DAVE E2EE, SSRC-to-user mapping, Opus decode, VAD, PCM buffering. | ✅ |
| voice/follow.py | Core | Voice follow-user orchestration — tracks configured users, multi-user handoff, allowed-channel enforcement, bounded reconciliation. | ✅ |
| voice/manager.py | Core | Per-guild voice lifecycle with Lock, auto-timeout, listen loop, STT processing, display_name resolution, delegates follow-user to follow.py. | ✅ |
| voice/player.py | Core | FFmpeg audio playback with echo prevention (pauses receiver during play). | ✅ |
