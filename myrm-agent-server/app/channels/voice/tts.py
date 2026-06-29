"""Text-to-Speech synthesis for outbound Agent replies.

Supports multiple providers with automatic fallback to Edge TTS (free):
  1. OpenAI (gpt-4o-mini-tts)
  2. ElevenLabs (eleven_multilingual_v2)
  3. Fish Audio (s1 model, 2M+ community voices)
  4. MiniMax (speech-2.8-hd, cost-effective Asian language support)
  5. Edge TTS (Microsoft Neural, free, no API key)

[INPUT]
- channels.types::VoiceConfig, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- synthesize(): Text -> audio file path (Path)
- synthesize_stream(): Text -> AsyncGenerator[bytes] (streaming audio)

[POS]
Outbound text-to-speech. Called by Router based on TTSMode when sending Agent replies.
Synthesizes text to audio and sends via MediaAttachment(AUDIO).
Telegram uses Opus format (voice bubble); other platforms use default format. MP3。
Web playback uses synthesize_stream() for streaming。
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx

from app.channels.types import VoiceConfig

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "elevenlabs": "https://api.elevenlabs.io",
    "fish_audio": "https://api.fish.audio/v1",
    "minimax": "https://api.minimax.io/v1",
}

_DEFAULT_VOICES: dict[str, str] = {
    "openai": "alloy",
    "elevenlabs": "21m00Tcm4TlvDq8ikWAM",
    "fish_audio": "7f92f8afb8ec43bf81429cc1c9199cb1",
    "minimax": "English_expressive_narrator",
    "edge": "en-US-MichelleNeural",
}


def _resolve_base_url(config: VoiceConfig, provider: str) -> str:
    """Resolve the API base URL: config override (OpenAI only) > provider default.

    Custom base URL only applies to OpenAI provider since compatible endpoints
    (Kokoro, LocalAI, Azure) all follow the OpenAI API contract.
    Other providers have proprietary APIs with no compatible alternatives.
    """
    if provider == "openai" and config.tts_base_url:
        return config.tts_base_url.rstrip("/")
    return _DEFAULT_BASE_URLS.get(provider, "")


_MIN_TEXT_LENGTH = 10
_TTS_TIMEOUT = 30.0
_STREAM_CHUNK_SIZE = 4096


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def synthesize(
    text: str,
    config: VoiceConfig,
    *,
    output_format: str = "mp3",
) -> Path | None:
    """Synthesize text to an audio file. Falls back to Edge TTS on failure."""
    if len(text) < _MIN_TEXT_LENGTH:
        logger.warning("TTS: text too short (%d chars), skipping", len(text))
        return None

    if len(text) > config.tts_max_length:
        logger.warning("TTS: text too long (%d > %d chars), skipping", len(text), config.tts_max_length)
        return None

    if config.tts_summary_enabled and len(text) > config.tts_summary_threshold:
        summarized = await _summarize_for_tts(text, config)
        if summarized:
            text = summarized

    provider = config.tts_provider.lower()
    try:
        if provider == "edge":
            return await _synthesize_edge(text, config)
        return await _synthesize_api(text, config, provider, output_format)
    except Exception:
        logger.exception("TTS: primary provider '%s' failed", provider)

    if provider != "edge":
        try:
            logger.warning("TTS: falling back to Edge TTS (free)")
            return await _synthesize_edge(text, config)
        except Exception:
            logger.exception("TTS: Edge TTS fallback also failed")
    return None


async def synthesize_stream(
    text: str,
    config: VoiceConfig,
) -> AsyncGenerator[bytes]:
    """Stream-synthesize text to MP3 audio chunks. Falls back to Edge TTS."""
    if len(text) < _MIN_TEXT_LENGTH:
        logger.warning("TTS stream: text too short (%d chars), skipping", len(text))
        return

    provider = config.tts_provider.lower()
    stream_fn = _STREAM_PROVIDERS.get(provider)

    if stream_fn:
        try:
            async for chunk in stream_fn(text, config):
                yield chunk
            return
        except Exception:
            logger.exception("TTS stream: provider '%s' failed, falling back", provider)

    if provider != "edge":
        try:
            async for chunk in _stream_edge(text, config):
                yield chunk
            return
        except Exception:
            logger.exception("TTS stream: edge fallback also failed")


# ---------------------------------------------------------------------------
# Request builders (shared between streaming and non-streaming)
# ---------------------------------------------------------------------------


def _openai_request(config: VoiceConfig, text: str, fmt: str):
    voice = config.tts_voice or _DEFAULT_VOICES["openai"]
    base = _resolve_base_url(config, "openai")
    url = f"{base}/audio/speech"
    headers = {"Authorization": f"Bearer {config.tts_api_key}", "Content-Type": "application/json"}
    body: dict[str, object] = {"model": "gpt-4o-mini-tts", "input": text, "voice": voice, "response_format": fmt}
    if config.tts_speed != 1.0:
        body["speed"] = config.tts_speed
    return url, headers, body


def _elevenlabs_request(config: VoiceConfig, text: str, stream: bool):
    voice_id = config.tts_voice or _DEFAULT_VOICES["elevenlabs"]
    base_url = _resolve_base_url(config, "elevenlabs")
    endpoint = f"{base_url}/v1/text-to-speech/{voice_id}"
    url = f"{endpoint}/stream" if stream else endpoint
    headers = {"xi-api-key": config.tts_api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"}
    params = {"output_format": "mp3_44100_128"}
    body = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True},
    }
    return url, headers, params, body


def _fish_audio_request(config: VoiceConfig, text: str, fmt: str):
    voice_id = config.tts_voice or _DEFAULT_VOICES["fish_audio"]
    base = _resolve_base_url(config, "fish_audio")
    url = f"{base}/tts"
    headers = {"Authorization": f"Bearer {config.tts_api_key}", "model": "s1"}
    body = {"text": text, "reference_id": voice_id, "format": fmt, "latency": "normal"}
    return url, headers, body


def _minimax_request(config: VoiceConfig, text: str, *, stream: bool):
    voice_id = config.tts_voice or _DEFAULT_VOICES["minimax"]
    base = _resolve_base_url(config, "minimax")
    url = f"{base}/t2a_v2"
    headers = {"Authorization": f"Bearer {config.tts_api_key}", "Content-Type": "application/json"}
    body = {
        "model": "speech-2.8-hd",
        "text": text,
        "stream": stream,
        "language_boost": "auto",
        "voice_setting": {"voice_id": voice_id, "speed": config.tts_speed, "vol": 1.0, "pitch": config.tts_pitch},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
    }
    return url, headers, body


# ---------------------------------------------------------------------------
# Non-streaming provider implementations
# ---------------------------------------------------------------------------


async def _synthesize_api(text: str, config: VoiceConfig, provider: str, output_format: str) -> Path:
    """Unified non-streaming synthesis for API-based providers."""
    fmt = "opus" if output_format == "opus" else "mp3"

    if provider == "openai":
        url, headers, body = _openai_request(config, text, fmt)
        async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            return _write_temp(resp.content, f".{fmt}")

    if provider == "elevenlabs":
        url, headers, params, body = _elevenlabs_request(config, text, stream=False)
        async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, params=params, json=body)
            resp.raise_for_status()
            return _write_temp(resp.content, ".mp3")

    if provider == "fish_audio":
        url, headers, body = _fish_audio_request(config, text, fmt)
        async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            return _write_temp(resp.content, f".{fmt}")

    if provider == "minimax":
        url, headers, body = _minimax_request(config, text, stream=False)
        async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

        base_resp = data.get("base_resp", {})
        if base_resp.get("status_code", 0) != 0:
            raise ValueError(f"MiniMax TTS error: {base_resp.get('status_msg', 'unknown')}")
        audio_hex = data.get("data", {}).get("audio", "")
        if not audio_hex:
            raise ValueError("MiniMax TTS returned empty audio")
        return _write_temp(bytes.fromhex(audio_hex), ".mp3")

    logger.warning("TTS: unknown provider '%s', falling back to edge", provider)
    raise ValueError(f"Unknown provider: {provider}")


async def _synthesize_edge(text: str, config: VoiceConfig) -> Path:
    import edge_tts

    voice = config.tts_voice or _DEFAULT_VOICES["edge"]
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    output_path = Path(tmp.name)

    rate = f"{(config.tts_speed - 1.0) * 100:+.0f}%" if config.tts_speed != 1.0 else "+0%"
    pitch = f"{config.tts_pitch:+.0f}Hz" if config.tts_pitch != 0.0 else "+0Hz"
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(output_path))

    file_size = output_path.stat().st_size
    if file_size < 100:
        output_path.unlink(missing_ok=True)
        raise ValueError("Edge TTS produced empty audio")

    logger.warning("TTS: edge ok (voice=%s, bytes=%d)", voice, file_size)
    return output_path


# ---------------------------------------------------------------------------
# Streaming provider implementations
# ---------------------------------------------------------------------------


async def _stream_openai(text: str, config: VoiceConfig) -> AsyncGenerator[bytes]:
    url, headers, body = _openai_request(config, text, "mp3")
    async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(_STREAM_CHUNK_SIZE):
                yield chunk


async def _stream_elevenlabs(text: str, config: VoiceConfig) -> AsyncGenerator[bytes]:
    url, headers, params, body = _elevenlabs_request(config, text, stream=True)
    async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
        async with client.stream("POST", url, headers=headers, params=params, json=body) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(_STREAM_CHUNK_SIZE):
                yield chunk


async def _stream_fish_audio(text: str, config: VoiceConfig) -> AsyncGenerator[bytes]:
    url, headers, body = _fish_audio_request(config, text, "mp3")
    async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(_STREAM_CHUNK_SIZE):
                yield chunk


async def _stream_minimax(text: str, config: VoiceConfig) -> AsyncGenerator[bytes]:
    """MiniMax streaming returns SSE with hex-encoded audio in each event."""
    url, headers, body = _minimax_request(config, text, stream=True)
    async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            resp.raise_for_status()
            buffer = ""
            async for raw in resp.aiter_text():
                buffer += raw
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        return
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    audio_hex = data.get("data", {}).get("audio", "")
                    if audio_hex:
                        yield bytes.fromhex(audio_hex)


async def _stream_edge(text: str, config: VoiceConfig) -> AsyncGenerator[bytes]:
    import edge_tts

    voice = config.tts_voice or _DEFAULT_VOICES["edge"]
    rate = f"{(config.tts_speed - 1.0) * 100:+.0f}%" if config.tts_speed != 1.0 else "+0%"
    pitch = f"{config.tts_pitch:+.0f}Hz" if config.tts_pitch != 0.0 else "+0Hz"
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    async for event in communicate.stream():
        if event["type"] == "audio":
            yield event["data"]


_STREAM_PROVIDERS = {
    "openai": _stream_openai,
    "elevenlabs": _stream_elevenlabs,
    "fish_audio": _stream_fish_audio,
    "minimax": _stream_minimax,
    "edge": _stream_edge,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_temp(data: bytes, suffix: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)


_SUMMARY_PROMPT = (
    "Summarize the following text for audio playback. "
    "Keep key information, be concise, and stay under 300 words. "
    "Output the summary directly without any preamble.\n\n"
)

_SUMMARY_TIMEOUT = 15.0


async def _summarize_for_tts(text: str, config: VoiceConfig) -> str | None:
    """Summarize long text using LLM before TTS synthesis."""
    try:
        from litellm import acompletion

        model = config.tts_summary_model or "gpt-4o-mini"
        resp = await acompletion(
            model=model,
            messages=[{"role": "user", "content": f"{_SUMMARY_PROMPT}{text}"}],
            max_tokens=500,
            temperature=0.3,
            timeout=_SUMMARY_TIMEOUT,
        )
        summary = resp.choices[0].message.content.strip()
        if not summary:
            return None

        logger.warning("TTS: summarized %d → %d chars (model=%s)", len(text), len(summary), model)
        return summary
    except Exception:
        logger.exception("TTS: summarization failed, using original text")
        return None
