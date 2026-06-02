# voice/

## Overview
Discord voice channel support. Provides voice receive, playback, and lifecycle management. Requires discord.py[voice] and PyNaCl.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Discord voice module public API. | — |
| follow.py | Core | Voice Follow-User orchestration — tracks configured users across voice channels, multi-user handoff, allowed-channel enforcement, bounded reconciliation. | ✅ |
| manager.py | Core | Voice channel connection manager — join/leave lifecycle, Wake-Word TTL state machine, Anti-Reflection (barge-in) logic, delegates follow-user to `follow.py`. | ✅ |
| player.py | Core | Audio playback engine for voice channels. | ✅ |
| receiver.py | Core | Audio receiver — captures incoming voice data, outputs in-memory WAV bytes. | ✅ |

## Architecture Notes
- **Zero-Disk I/O**: `receiver.py` wraps raw PCM audio into WAV format fully in-memory (`io.BytesIO`), bypassing `ffmpeg` subprocesses to minimize TTFT latency.
- **True Barge-in (Anti-Echo)**: `player.py` does not block `receiver.py` while speaking. `manager.py` compares incoming text with current TTS output (Levenshtein similarity) to discard echo, allowing actual user interruptions to stop playback.
- **Cocktail Party TTL**: Features an ASLEEP/AWAKE state machine. When asleep, only transcribes and responds if wake words are detected. Enters an active session (AWAKE) for 30s upon trigger to save tokens.
- **Voice Follow-User**: `follow.py` via `VoiceFollowManager` automatically tracks configured Discord users across voice channels. Uses `VoiceJoinLeave` Protocol for clean dependency inversion. Supports multi-user handoff (when one followed user leaves, bot switches to another), allowed-channel whitelist enforcement, bot movement protection (leaves if moved to non-allowed channel), and bounded reconciliation (10s + jitter periodic polling to compensate for missed WebSocket events).

## Key Dependencies

- `channels::providers::discord` (Discord client)
