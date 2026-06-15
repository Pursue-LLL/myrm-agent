# voice/

## Overview
Voice subsystem: STT transcription, TTS synthesis, and voice message routing.

Supports 5 STT providers (local/openai/groq/deepgram/xai) with automatic fallback,
and 5 TTS providers (edge/openai/elevenlabs/fish_audio/minimax) with Edge TTS free fallback.
Video attachments (.mp4/.webm) are transcribed via the same STT pipeline.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Voice subsystem: STT transcription, TTS synthesis, and voice message routing. | — |
| handler.py | Core | Voice processing module. STT for voice and video, TTS synthesis, download dispatching. | ✅ |
| stt.py | Core | Inbound speech-to-text (5 providers). Supports in-memory byte inputs for zero-disk latency. | ✅ |
| tts.py | Core | Outbound text-to-speech. Called by Router based on TTSMode when sending Agent replies. | ✅ |

## Architecture Notes

- **STT Fallback**: mirrors TTS pattern. Primary fails → local if available (free fallback); local fails → cloud API.
- **Local STT**: uses faster-whisper (optional dependency `local-stt`). Singleton model loaded once, reused across calls.
- **Zero-Disk Streaming**: `stt.py` accepts `audio_bytes` in memory to eliminate physical file I/O latency, fully utilized by the Discord provider.
- **Streaming STT**: Deepgram WebSocket (server layer), local uses batch mode only.
- **xAI Grok STT**: dedicated `_transcribe_xai()` for the non-OpenAI-compatible `/v1/stt` endpoint with ITN support.
- **stt_base_url**: `VoiceConfig.stt_base_url` enables any OpenAI-compatible STT endpoint (Mistral, Azure, self-hosted Whisper).
- **Video Transcription**: `handler.transcribe_video_inbound()` downloads video and reuses the STT pipeline; `.mp4`/`.webm` are natively supported by STT providers.
