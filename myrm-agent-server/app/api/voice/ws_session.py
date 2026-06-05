"""Full-duplex voice session WebSocket endpoint.

Provides bidirectional audio streaming for voice conversations with two modes:

  **audio_only** (default): Pure STT + TTS I/O. Agent calls handled by frontend.
  **agent_bridge**: STT → server-side Agent → TTS. Eliminates frontend roundtrip.

Protocol (JSON text frames + binary audio frames):
  C→S: {"type": "config", "keyterms": [...], "mode": "audio_only"|"agent_bridge",
         "agent_id": "...", "chat_id": "..."}
  C→S: binary audio chunks (webm/opus from MediaRecorder)
  C→S: {"type": "tts", "text": "..."}       — request TTS synthesis (audio_only)
  C→S: {"type": "tts_cancel"}               — cancel current TTS (barge-in)
  C→S: {"type": "close"}                    — end session

  S→C: {"type": "stt_interim", "text": "..."}
  S→C: {"type": "stt_final", "text": "..."}
  S→C: {"type": "tts_start"}
  S→C: binary audio chunks (mp3 from streaming TTS)
  S→C: {"type": "tts_end"}
  S→C: {"type": "agent_thinking", "turn_id": "..."}     — agent_bridge only
  S→C: {"type": "agent_response", "text": "...", ...}   — agent_bridge only
  S→C: {"type": "agent_tool_use", "tool_name": "..."}   — agent_bridge only
  S→C: {"type": "agent_done", "turn_id": "..."}         — agent_bridge only
  S→C: {"type": "agent_error", "message": "..."}        — agent_bridge only
  S→C: {"type": "error", "message": "..."}

[INPUT]
- app.api.stt.ws_stream: Deepgram proxy pattern (reused)
- app.api.voice.agent_bridge::VoiceAgentBridge (POS: Agent execution bridge for voice)
- app.core.infra.ws_origin_guard::verify_ws_origin (POS: WebSocket Origin guard)
- app.core.channel_bridge.config_loader (POS: user config loader)
- app.channels.voice.tts::synthesize_stream (POS: streaming TTS)
- app.channels.voice.stt::transcribe (POS: batch STT fallback)

[OUTPUT]
- ws_voice_session: Full-duplex voice WebSocket (audio_only or agent_bridge)

[POS]
Full-duplex voice I/O endpoint. Supports two modes: audio_only (pure STT+TTS)
and agent_bridge (server-side Agent execution with streaming TTS).
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
    from app.api.voice.agent_bridge import VoiceAgentBridge
    from app.channels.types import VoiceConfig

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_voice_enabled)])

_DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
_STREAMING_PROVIDERS = frozenset({"deepgram"})

_WS_CLOSE_NORMAL = 1000
_WS_CLOSE_ERROR = 1011
_MAX_AUDIO_CHUNK = 1024 * 1024
_SESSION_IDLE_TIMEOUT = 180.0


@router.websocket("/session")
async def ws_voice_session(ws: WebSocket) -> None:
    """Full-duplex voice session: concurrent STT streaming + on-demand TTS."""
    if not await verify_ws_origin(ws):
        return
    await ws.accept()

    try:
        config_msg = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
        client_config = json.loads(config_msg)
    except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
        await _close_ws(ws, _WS_CLOSE_ERROR, "Invalid config")
        return

    if client_config.get("type") != "config":
        await _close_ws(ws, _WS_CLOSE_ERROR, "First message must be type:config")
        return

    voice_config = await _load_voice_config(ws)
    if not voice_config:
        return

    mode = client_config.get("mode", "audio_only")

    if mode == "agent_bridge":
        from app.api.voice.agent_bridge import VoiceAgentBridge

        ws_send_lock = asyncio.Lock()
        bridge = VoiceAgentBridge(
            _ws=ws,
            _voice_config=voice_config,
            _agent_id=client_config.get("agent_id"),
            _chat_id=client_config.get("chat_id"),
            _ws_send_lock=ws_send_lock,
        )
        session = _VoiceSession(
            ws=ws,
            voice_config=voice_config,
            keyterms=client_config.get("keyterms", []),
            agent_bridge=bridge,
            ws_send_lock=ws_send_lock,
        )
    else:
        session = _VoiceSession(
            ws=ws,
            voice_config=voice_config,
            keyterms=client_config.get("keyterms", []),
        )

    await session.run()


class _VoiceSession:
    """Manages concurrent STT + TTS within a single WebSocket."""

    __slots__ = (
        "_ws",
        "_voice_config",
        "_keyterms",
        "_closed",
        "_tts_cancel_event",
        "_tts_queue",
        "_agent_bridge",
        "_ws_send_lock",
    )

    def __init__(
        self,
        ws: WebSocket,
        voice_config: VoiceConfig,
        keyterms: list[str],
        agent_bridge: VoiceAgentBridge | None = None,
        ws_send_lock: asyncio.Lock | None = None,
    ) -> None:
        self._ws = ws
        self._voice_config = voice_config
        self._keyterms = keyterms
        self._closed = False
        self._tts_cancel_event = asyncio.Event()
        self._tts_queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._agent_bridge = agent_bridge
        self._ws_send_lock = ws_send_lock or asyncio.Lock()

    async def run(self) -> None:
        """Main loop: run STT relay + TTS consumer concurrently."""
        provider = self._voice_config.stt_provider.lower()

        tts_task = asyncio.create_task(self._tts_consumer())

        try:
            if provider in _STREAMING_PROVIDERS:
                await self._run_streaming_stt()
            else:
                await self._run_batch_stt()
        finally:
            self._tts_queue.put_nowait(None)
            tts_task.cancel()
            try:
                await tts_task
            except asyncio.CancelledError:
                pass
            await _close_ws(self._ws, _WS_CLOSE_NORMAL, "Session ended")

    # ── STT: Streaming via Deepgram ──────────────────────────────────────

    async def _run_streaming_stt(self) -> None:
        params = [
            ("model", self._voice_config.stt_model or "nova-3"),
            ("smart_format", "true"),
            ("interim_results", "true"),
            ("endpointing", "300"),
            ("encoding", "opus"),
            ("sample_rate", "48000"),
        ]
        if self._voice_config.stt_language:
            params.append(("language", self._voice_config.stt_language))
        for term in self._keyterms:
            stripped = term.strip()
            if stripped:
                params.append(("keywords", f"{stripped}:2"))

        query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params)
        dg_url = f"{_DEEPGRAM_WS_URL}?{query}"

        try:
            import websockets

            async with websockets.connect(
                dg_url,
                additional_headers={"Authorization": f"Token {self._voice_config.stt_api_key}"},
                ping_interval=20,
                close_timeout=5,
            ) as dg_ws:
                audio_relay = asyncio.create_task(self._relay_client_audio(dg_ws))
                transcript_relay = asyncio.create_task(self._relay_deepgram_transcripts(dg_ws))

                done, pending = await asyncio.wait(
                    {audio_relay, transcript_relay},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

        except ImportError:
            logger.error("websockets package not installed for streaming STT")
            await self._send_json({"type": "error", "message": "STT provider unavailable"})
        except Exception:
            logger.exception("Deepgram WebSocket connection failed")
            await self._send_json({"type": "error", "message": "STT connection failed"})

    async def _relay_client_audio(self, dg_ws: object) -> None:
        """Forward audio from browser to Deepgram, handle control messages."""
        try:
            while not self._closed:
                try:
                    msg = await asyncio.wait_for(self._ws.receive(), timeout=_SESSION_IDLE_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.info("Voice session idle timeout")
                    break

                if msg.get("type") == "websocket.disconnect":
                    break

                if "bytes" in msg and msg["bytes"]:
                    data = msg["bytes"]
                    if len(data) <= _MAX_AUDIO_CHUNK:
                        await dg_ws.send(data)

                elif "text" in msg and msg["text"]:
                    self._handle_text_message(msg["text"])

        except WebSocketDisconnect:
            self._closed = True
        finally:
            try:
                await dg_ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass

    def _handle_text_message(self, text: str) -> None:
        """Parse and dispatch incoming JSON control messages."""
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return

        msg_type = parsed.get("type", "")

        if msg_type == "close":
            self._closed = True

        elif msg_type == "tts":
            tts_text = parsed.get("text", "").strip()
            if tts_text:
                self._tts_queue.put_nowait(tts_text)

        elif msg_type == "tts_cancel":
            self._tts_cancel_event.set()
            if self._agent_bridge:
                self._agent_bridge.cancel_tts()

    async def _relay_deepgram_transcripts(self, dg_ws: object) -> None:
        """Relay Deepgram transcription results to the browser."""
        try:
            async for raw in dg_ws:
                if isinstance(raw, bytes) or self._closed:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if data.get("type") != "Results":
                    continue

                channel = data.get("channel", {})
                alternatives = channel.get("alternatives", [])
                if not alternatives:
                    continue

                text = alternatives[0].get("transcript", "").strip()
                if not text:
                    continue

                is_final = data.get("is_final", False)
                if is_final and self._agent_bridge:
                    task = asyncio.create_task(self._agent_bridge.handle_stt_final(text))
                    task.add_done_callback(self._on_bridge_task_done)
                else:
                    event_type = "stt_final" if is_final else "stt_interim"
                    await self._send_json({"type": event_type, "text": text})

        except Exception:
            if not self._closed:
                logger.warning("Deepgram transcript relay error", exc_info=True)

    # ── TTS: Streaming synthesis consumer ────────────────────────────────

    async def _tts_consumer(self) -> None:
        """Consume TTS requests from the queue and stream audio back."""
        while not self._closed:
            text = await self._tts_queue.get()
            if text is None:
                break
            await self._stream_tts(text)

    async def _stream_tts(self, text: str) -> None:
        """Stream TTS audio chunks back to the browser."""
        self._tts_cancel_event.clear()
        await self._send_json({"type": "tts_start"})

        try:
            from app.channels.voice.tts import synthesize_stream

            async for chunk in synthesize_stream(text, self._voice_config):
                if self._tts_cancel_event.is_set() or self._closed:
                    break
                try:
                    async with self._ws_send_lock:
                        await self._ws.send_bytes(chunk)
                except (WebSocketDisconnect, RuntimeError):
                    self._closed = True
                    break

        except Exception:
            logger.exception("TTS streaming failed in voice session")

        await self._send_json({"type": "tts_end"})

    # ── STT: Batch fallback for non-streaming providers ──────────────────

    async def _run_batch_stt(self) -> None:
        """Batch STT for providers without streaming support."""
        await self._send_json(
            {
                "type": "info",
                "message": "streaming_unavailable",
                "fallback": "batch",
            }
        )

        try:
            while not self._closed:
                chunks: list[bytes] = []
                total_size = 0

                while True:
                    try:
                        msg = await asyncio.wait_for(self._ws.receive(), timeout=_SESSION_IDLE_TIMEOUT)
                    except asyncio.TimeoutError:
                        self._closed = True
                        return

                    if msg.get("type") == "websocket.disconnect":
                        self._closed = True
                        return

                    if "bytes" in msg and msg["bytes"]:
                        chunk = msg["bytes"]
                        total_size += len(chunk)
                        if total_size > 25 * 1024 * 1024:
                            await self._send_json(
                                {
                                    "type": "error",
                                    "message": "Audio too large",
                                }
                            )
                            return
                        chunks.append(chunk)

                    elif "text" in msg and msg["text"]:
                        self._handle_text_message(msg["text"])
                        if self._closed:
                            return
                        try:
                            parsed = json.loads(msg["text"])
                            if parsed.get("type") == "end_utterance":
                                break
                        except json.JSONDecodeError:
                            pass

                if not chunks:
                    continue

                audio_blob = b"".join(chunks)
                if len(audio_blob) < 1024:
                    continue

                text = await self._batch_transcribe(audio_blob)
                if text:
                    if self._agent_bridge:
                        task = asyncio.create_task(self._agent_bridge.handle_stt_final(text))
                        task.add_done_callback(self._on_bridge_task_done)
                    else:
                        await self._send_json({"type": "stt_final", "text": text})

        except WebSocketDisconnect:
            pass

    async def _batch_transcribe(self, audio_blob: bytes) -> str | None:
        """Transcribe audio blob using batch STT."""
        import tempfile
        from pathlib import Path

        from app.channels.voice.stt import transcribe

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(audio_blob)
            tmp_path = Path(tmp.name)

        try:
            result = await transcribe(tmp_path, self._voice_config)
            return result.text if result and result.text else None
        except Exception:
            logger.exception("Batch STT failed in voice session")
            return None
        finally:
            tmp_path.unlink(missing_ok=True)

    # ── Task error handling ──────────────────────────────────────────────

    def _on_bridge_task_done(self, task: asyncio.Task[None]) -> None:
        """Callback for fire-and-forget bridge tasks — log & relay errors."""
        exc = task.exception()
        if exc is None:
            return
        logger.error("Agent bridge task failed: %s", exc, exc_info=exc)
        if not self._closed:
            asyncio.create_task(self._send_json({"type": "error", "message": "Agent processing failed"}))

    # ── Helpers ──────────────────────────────────────────────────────────

    async def _send_json(self, data: dict[str, object]) -> None:
        if self._closed:
            return
        try:
            async with self._ws_send_lock:
                await self._ws.send_text(json.dumps(data, ensure_ascii=False))
        except (WebSocketDisconnect, RuntimeError):
            self._closed = True


async def _load_voice_config(ws: WebSocket) -> VoiceConfig | None:
    """Load VoiceConfig for voice session WebSocket."""
    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    user_id = getattr(ws.state, "user_id", "") or ""
    if not user_id:
        if get_deployment_capabilities().requires_strict_ws_auth:
            await _send_json_to_ws(ws, {"type": "error", "message": "Authentication required"})
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

    await _send_json_to_ws(ws, {"type": "error", "message": "Voice not configured"})
    await _close_ws(ws, _WS_CLOSE_ERROR, "Voice not configured")
    return None


async def _send_json_to_ws(ws: WebSocket, data: dict[str, object]) -> None:
    try:
        await ws.send_text(json.dumps(data))
    except (WebSocketDisconnect, RuntimeError):
        pass


async def _close_ws(ws: WebSocket, code: int, reason: str) -> None:
    try:
        await ws.close(code=code, reason=reason)
    except Exception:
        pass
