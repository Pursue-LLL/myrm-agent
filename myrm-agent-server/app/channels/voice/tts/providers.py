"""各 TTS 提供方的请求构造与流式实现。

[POS]
voice tts 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx

from app.channels.types import VoiceConfig

from .common import (
    _DEFAULT_VOICES,
    _PIPER_INSTALL_HINT,
    _STREAM_CHUNK_SIZE,
    _TTS_TIMEOUT,
    _import_edge_tts,
    _resolve_base_url,
    _write_temp,
    is_piper_available,
)

logger = logging.getLogger(__name__)


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

    if provider == "voicebox":
        base_url = _resolve_base_url(config, "voicebox")
        url = f"{base_url}/tts"
        body = {
            "text": text,
            "voice": config.tts_voice or _DEFAULT_VOICES["voicebox"],
            "speed": config.tts_speed,
        }
        async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return _write_temp(resp.content, ".mp3")

    if provider == "piper":
        return await _synthesize_piper(text, config)

    logger.warning("TTS: unknown provider '%s', falling back to edge", provider)
    raise ValueError(f"Unknown provider: {provider}")


async def _synthesize_piper(text: str, config: VoiceConfig) -> Path:
    """Synthesize text using local Piper TTS."""
    if not is_piper_available():
        raise ImportError(f"piper is not installed. Install with: {_PIPER_INSTALL_HINT}")

    import piper

    voice_name = config.tts_voice or _DEFAULT_VOICES["piper"]
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    output_path = Path(tmp.name)

    voice = piper.PiperVoice.load(voice_name)
    with open(output_path, "wb") as f:
        voice.synthesize(text, f)

    file_size = output_path.stat().st_size
    if file_size < 100:
        output_path.unlink(missing_ok=True)
        raise ValueError("Piper TTS produced empty audio")

    logger.warning("TTS: piper ok (voice=%s, bytes=%d)", voice_name, file_size)
    return output_path


async def _synthesize_edge(text: str, config: VoiceConfig) -> Path:
    edge_tts = _import_edge_tts()

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
    edge_tts = _import_edge_tts()

    voice = config.tts_voice or _DEFAULT_VOICES["edge"]
    rate = f"{(config.tts_speed - 1.0) * 100:+.0f}%" if config.tts_speed != 1.0 else "+0%"
    pitch = f"{config.tts_pitch:+.0f}Hz" if config.tts_pitch != 0.0 else "+0Hz"
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    async for event in communicate.stream():
        if event["type"] == "audio":
            yield event["data"]


async def _stream_voicebox(text: str, config: VoiceConfig) -> AsyncGenerator[bytes]:
    base_url = _resolve_base_url(config, "voicebox")
    url = f"{base_url}/tts/stream"
    body = {
        "text": text,
        "voice": config.tts_voice or _DEFAULT_VOICES["voicebox"],
        "speed": config.tts_speed,
    }
    async with httpx.AsyncClient(timeout=_TTS_TIMEOUT) as client:
        async with client.stream("POST", url, json=body) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(_STREAM_CHUNK_SIZE):
                yield chunk


async def _stream_piper(text: str, config: VoiceConfig) -> AsyncGenerator[bytes]:
    """Stream Piper TTS synthesis chunks."""
    if not is_piper_available():
        raise ImportError(f"piper is not installed. Install with: {_PIPER_INSTALL_HINT}")

    import piper

    voice_name = config.tts_voice or _DEFAULT_VOICES["piper"]
    voice = piper.PiperVoice.load(voice_name)
    for chunk in voice.synthesize_stream_raw(text):
        yield chunk


_STREAM_PROVIDERS = {
    "openai": _stream_openai,
    "elevenlabs": _stream_elevenlabs,
    "fish_audio": _stream_fish_audio,
    "minimax": _stream_minimax,
    "edge": _stream_edge,
    "voicebox": _stream_voicebox,
    "piper": _stream_piper,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
