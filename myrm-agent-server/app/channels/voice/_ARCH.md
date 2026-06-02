# voice/

## Overview
Voice subsystem: STT transcription, TTS synthesis, and voice message routing.

Supports 4 STT providers (local/openai/groq/deepgram) with automatic fallback,
and 5 TTS providers (edge/openai/elevenlabs/fish_audio/minimax) with Edge TTS free fallback.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Voice subsystem: STT transcription, TTS synthesis, and voice message routing. | — |
| handler.py | Core | Voice processing module. Extracted from Router core routing logic as a collection | ✅ |
| stt.py | Core | Inbound speech-to-text. Supports in-memory byte inputs for zero-disk latency. | ✅ |
| tts.py | Core | Outbound text-to-speech. Called by Router based on TTSMode when sending Agent replies. | ✅ |

## Architecture Notes

- **STT Fallback**: mirrors TTS pattern. Primary fails → local if available (free fallback); local fails → cloud API.
- **Local STT**: uses faster-whisper (optional dependency `local-stt`). Singleton model loaded once, reused across calls.
- **Zero-Disk Streaming**: `stt.py` accepts `audio_bytes` in memory to eliminate physical file I/O latency, fully utilized by the Discord provider.
- **Streaming STT**: Deepgram WebSocket (server layer), local uses batch mode only.
