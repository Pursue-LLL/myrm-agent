"""WebSocket STT streaming endpoint.

Proxies audio from browser → backend WebSocket → STT provider (Deepgram/Groq).
Returns interim and final transcripts in real-time.

Protocol:
  1. Client opens WS to /ws/stt/stream
  2. Client sends JSON config: {"keyterms": ["term1", ...]}
  3. Client sends binary audio chunks (webm/opus)
  4. Server streams back: {"type": "transcript", "text": "...", "is_final": true/false}
  5. Client sends {"action": "close"} to end, or server closes on provider disconnect
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING
from urllib.parse import quote

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.dependencies import verify_voice_enabled
from app.core.infra.ws_origin_guard import verify_ws_origin

if TYPE_CHECKING:
    from app.channels.types import VoiceConfig

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_voice_enabled)])

_DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
_STREAMING_PROVIDERS = frozenset({"deepgram"})

_WS_CLOSE_NORMAL = 1000
_WS_CLOSE_ERROR = 1011
_MAX_AUDIO_CHUNK = 1024 * 1024  # 1MB per chunk
_SESSION_IDLE_TIMEOUT = 120.0  # Close WS if no data received for 120s


@router.websocket("/stream")
async def stt_stream(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time STT streaming."""
    if not await verify_ws_origin(ws):
        return
    await ws.accept()

    try:
        config_msg = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
        client_config = json.loads(config_msg)
    except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
        await _close_ws(ws, _WS_CLOSE_ERROR, "Invalid config")
        return

    keyterms: list[str] = client_config.get("keyterms", [])

    voice_config = await _load_voice_config_from_ws(ws)
    if not voice_config:
        await _close_ws(ws, _WS_CLOSE_ERROR, "STT not configured")
        return

    provider = voice_config.stt_provider.lower()

    if provider in _STREAMING_PROVIDERS:
        await _stream_via_deepgram(ws, voice_config, keyterms)
    else:
        await _batch_fallback(ws, voice_config)


async def _stream_via_deepgram(
    ws: WebSocket,
    config: VoiceConfig,
    keyterms: list[str],
) -> None:
    """Proxy audio to Deepgram WebSocket and relay transcripts back."""
    params = [
        ("model", config.stt_model or "nova-3"),
        ("smart_format", "true"),
        ("interim_results", "true"),
        ("endpointing", "300"),
        ("encoding", "opus"),
        ("sample_rate", "48000"),
    ]
    if config.stt_language:
        params.append(("language", config.stt_language))
    for term in keyterms:
        stripped = term.strip()
        if stripped:
            params.append(("keywords", f"{stripped}:2"))

    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params)
    dg_url = f"{_DEEPGRAM_WS_URL}?{query}"

    try:
        import websockets

        async with websockets.connect(
            dg_url,
            additional_headers={"Authorization": f"Token {config.stt_api_key}"},
            ping_interval=20,
            close_timeout=5,
        ) as dg_ws:
            receive_task = asyncio.create_task(_relay_client_audio(ws, dg_ws))
            send_task = asyncio.create_task(_relay_deepgram_transcripts(ws, dg_ws))

            done, pending = await asyncio.wait(
                {receive_task, send_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, (WebSocketDisconnect, asyncio.CancelledError)):
                    logger.warning("STT stream task error: %s", exc)

    except ImportError:
        logger.error("websockets package not installed, falling back to batch STT")
        await _batch_fallback(ws, config)
    except Exception:
        logger.exception("Deepgram WebSocket connection failed")
        await _send_json(ws, {"type": "error", "message": "STT provider connection failed"})
        await _close_ws(ws, _WS_CLOSE_ERROR, "Provider error")


async def _relay_client_audio(ws: WebSocket, dg_ws: object) -> None:
    """Forward audio chunks from client WebSocket to Deepgram."""
    import websockets

    assert isinstance(dg_ws, websockets.ClientConnection)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=_SESSION_IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                logger.info("STT session idle timeout, closing")
                break

            if msg.get("type") == "websocket.disconnect":
                break

            if "bytes" in msg and msg["bytes"]:
                data = msg["bytes"]
                if len(data) > _MAX_AUDIO_CHUNK:
                    continue
                await dg_ws.send(data)

            elif "text" in msg and msg["text"]:
                try:
                    parsed = json.loads(msg["text"])
                    if parsed.get("action") == "close":
                        await dg_ws.send(json.dumps({"type": "CloseStream"}))
                        break
                except json.JSONDecodeError:
                    pass
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await dg_ws.send(json.dumps({"type": "CloseStream"}))
        except Exception:
            pass


async def _relay_deepgram_transcripts(ws: WebSocket, dg_ws: object) -> None:
    """Relay Deepgram transcription results back to client."""
    import websockets

    assert isinstance(dg_ws, websockets.ClientConnection)
    try:
        async for raw in dg_ws:
            if isinstance(raw, bytes):
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")
            if msg_type != "Results":
                continue

            channel = data.get("channel", {})
            alternatives = channel.get("alternatives", [])
            if not alternatives:
                continue

            text = alternatives[0].get("transcript", "").strip()
            if not text:
                continue

            is_final = data.get("is_final", False)
            await _send_json(
                ws,
                {
                    "type": "transcript",
                    "text": text,
                    "is_final": is_final,
                },
            )
    except websockets.exceptions.ConnectionClosed:
        pass
    except WebSocketDisconnect:
        pass


async def _batch_fallback(ws: WebSocket, config: VoiceConfig) -> None:
    """For providers that don't support streaming (e.g. OpenAI Whisper).
    Collect all audio, transcribe in batch, return final result."""
    await _send_json(
        ws,
        {
            "type": "info",
            "message": "streaming_unavailable",
            "fallback": "batch",
        },
    )

    chunks: list[bytes] = []
    total_size = 0

    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=_SESSION_IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                logger.info("Batch STT session idle timeout, closing")
                break

            if msg.get("type") == "websocket.disconnect":
                break

            if "bytes" in msg and msg["bytes"]:
                chunk = msg["bytes"]
                total_size += len(chunk)
                if total_size > 25 * 1024 * 1024:
                    await _send_json(ws, {"type": "error", "message": "Audio too large"})
                    break
                chunks.append(chunk)

            elif "text" in msg and msg["text"]:
                try:
                    parsed = json.loads(msg["text"])
                    if parsed.get("action") == "close":
                        break
                except json.JSONDecodeError:
                    pass
    except WebSocketDisconnect:
        pass

    if not chunks:
        await _close_ws(ws, _WS_CLOSE_NORMAL, "No audio")
        return

    audio_blob = b"".join(chunks)
    if len(audio_blob) < 1024:
        await _close_ws(ws, _WS_CLOSE_NORMAL, "Audio too short")
        return

    try:
        import tempfile
        from pathlib import Path

        from app.channels.voice.stt import transcribe

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(audio_blob)
            tmp_path = Path(tmp.name)

        try:
            result = await transcribe(tmp_path, config)
            if result and result.text:
                await _send_json(
                    ws,
                    {
                        "type": "transcript",
                        "text": result.text,
                        "is_final": True,
                    },
                )
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:
        logger.exception("Batch STT fallback failed")
        await _send_json(ws, {"type": "error", "message": "Transcription failed"})

    await _close_ws(ws, _WS_CLOSE_NORMAL, "Done")


async def _load_voice_config_from_ws(ws: WebSocket) -> VoiceConfig | None:
    """Load VoiceConfig for WebSocket connections.

    Authentication is provided by HTTP middleware during the WebSocket upgrade.
    Sandbox mode rejects unauthenticated connections; local mode falls back to the
    fixed sandbox user/workspace id.
    """
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    user_id = getattr(ws.state, "user_id", "") or ""
    if not user_id:
        if get_deployment_capabilities().requires_strict_ws_auth:
            await _send_json(ws, {"type": "error", "message": "Authentication required"})
            await _close_ws(ws, _WS_CLOSE_ERROR, "Unauthorized")
            return None
        user_id = "sandbox"

    try:
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import extract_voice_config

        configs = await load_user_configs()
        voice_config = extract_voice_config(configs.voice_dict)
        if voice_config and voice_config.stt_enabled:
            return voice_config
    except Exception:
        logger.warning("Failed to load voice config for WS user %s", user_id)

    await _send_json(ws, {"type": "error", "message": "STT not configured"})
    await _close_ws(ws, _WS_CLOSE_ERROR, "STT not configured")
    return None


async def _send_json(ws: WebSocket, data: dict[str, object]) -> None:
    """Send JSON message to client WebSocket, ignoring disconnects."""
    try:
        await ws.send_text(json.dumps(data))
    except (WebSocketDisconnect, RuntimeError):
        pass


async def _close_ws(ws: WebSocket, code: int, reason: str) -> None:
    """Close WebSocket connection gracefully."""
    try:
        await ws.close(code=code, reason=reason)
    except Exception:
        pass
