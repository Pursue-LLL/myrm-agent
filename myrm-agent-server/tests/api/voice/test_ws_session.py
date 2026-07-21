"""Integration tests for the full-duplex voice session WebSocket endpoint.

Covers:
  - Config handshake (valid, missing, wrong type)
  - TTS request/cancel flow with barge-in
  - Streaming STT with mocked Deepgram WS
  - Batch STT fallback
  - _load_voice_config (sandbox vs local)
  - Control message handling
  - Audio chunk size limits
  - _send_json error handling
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.voice.ws_session import _close_ws, _send_json_to_ws, _VoiceSession, router


@dataclass(frozen=True, slots=True)
class _FakeVoiceConfig:
    stt_enabled: bool = True
    stt_provider: str = "deepgram"
    stt_api_key: str = "test-api-key"
    stt_model: str = "nova-3"
    stt_language: str | None = "en"
    tts_mode: str = "always"
    tts_provider: str = "edge"
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_voice: str = "en-US-AriaNeural"
    tts_max_length: int = 4000


@dataclass(frozen=True, slots=True)
class _FakeVoiceConfigBatch:
    stt_enabled: bool = True
    stt_provider: str = "openai"
    stt_api_key: str = "test-key"
    stt_model: str = "whisper-1"
    stt_language: str | None = None
    tts_mode: str = "always"
    tts_provider: str = "edge"
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_voice: str = ""
    tts_max_length: int = 4000


@dataclass(frozen=True, slots=True)
class _FakeVoiceConfigDisabled:
    stt_enabled: bool = False
    stt_provider: str = "openai"
    stt_api_key: str = ""
    stt_model: str = ""
    stt_language: str | None = None
    tts_mode: str = "off"
    tts_provider: str = ""
    tts_api_key: str = ""
    tts_base_url: str = ""
    tts_voice: str = ""
    tts_max_length: int = 4000


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/ws/voice")
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


def _patch_voice_config(config: object):
    return patch(
        "app.api.voice.ws_session._load_voice_config",
        new_callable=AsyncMock,
        return_value=config,
    )


def _patch_sandbox(is_sandbox: bool = False):
    return patch("app.config.deploy_mode.is_sandbox", return_value=is_sandbox)


class _FakeDgWs:
    """Fake Deepgram WebSocket that yields pre-configured transcript responses."""

    def __init__(
        self,
        responses: list[str] | None = None,
        hang_after_responses: bool = False,
    ) -> None:
        self._responses = responses or []
        self._sent: list[bytes | str] = []
        self._hang_after = hang_after_responses
        self._closed_event = asyncio.Event()

    async def send(self, data: bytes | str) -> None:
        self._sent.append(data)
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                if parsed.get("type") == "CloseStream":
                    self._closed_event.set()
            except json.JSONDecodeError:
                pass

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        for resp in self._responses:
            yield resp
        if self._hang_after:
            await self._closed_event.wait()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class TestConfigHandshake:
    """Tests for the initial config message handshake."""

    def test_valid_config_accepted(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfig()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config", "keyterms": ["test"]}))
                ws.send_text(json.dumps({"type": "close"}))

    def test_missing_config_type_rejects(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfig()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"keyterms": []}))

    def test_invalid_json_closes(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfig()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text("not-json{{{")

    def test_voice_not_configured_rejects(self, client: TestClient) -> None:
        with _patch_voice_config(None):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))

    def test_config_with_empty_keyterms(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfig()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config", "keyterms": []}))
                ws.send_text(json.dumps({"type": "close"}))


class TestStreamingSTT:
    """Tests for the streaming STT path (Deepgram mock)."""

    def test_streaming_stt_relays_transcripts(self, client: TestClient) -> None:
        dg_response = json.dumps(
            {
                "type": "Results",
                "is_final": True,
                "channel": {"alternatives": [{"transcript": "hello world"}]},
            }
        )
        fake_dg = _FakeDgWs(responses=[dg_response])

        with (
            _patch_voice_config(_FakeVoiceConfig()),
            patch("websockets.connect", return_value=fake_dg),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config", "keyterms": ["test"]}))

                msg = ws.receive_text()
                data = json.loads(msg)
                assert data["type"] == "stt_final"
                assert data["text"] == "hello world"

                ws.send_text(json.dumps({"type": "close"}))

    def test_streaming_stt_interim_results(self, client: TestClient) -> None:
        dg_response = json.dumps(
            {
                "type": "Results",
                "is_final": False,
                "channel": {"alternatives": [{"transcript": "partial"}]},
            }
        )
        fake_dg = _FakeDgWs(responses=[dg_response])

        with (
            _patch_voice_config(_FakeVoiceConfig()),
            patch("websockets.connect", return_value=fake_dg),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))

                msg = ws.receive_text()
                data = json.loads(msg)
                assert data["type"] == "stt_interim"
                assert data["text"] == "partial"

                ws.send_text(json.dumps({"type": "close"}))

    def test_streaming_stt_empty_transcript_skipped(self, client: TestClient) -> None:
        dg_response = json.dumps(
            {
                "type": "Results",
                "is_final": True,
                "channel": {"alternatives": [{"transcript": "  "}]},
            }
        )
        fake_dg = _FakeDgWs(responses=[dg_response])

        with (
            _patch_voice_config(_FakeVoiceConfig()),
            patch("websockets.connect", return_value=fake_dg),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.send_text(json.dumps({"type": "close"}))

    def test_streaming_stt_non_results_ignored(self, client: TestClient) -> None:
        dg_response = json.dumps({"type": "Metadata", "model_info": {}})
        fake_dg = _FakeDgWs(responses=[dg_response])

        with (
            _patch_voice_config(_FakeVoiceConfig()),
            patch("websockets.connect", return_value=fake_dg),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.send_text(json.dumps({"type": "close"}))

    def test_streaming_stt_connection_failure(self, client: TestClient) -> None:
        with (
            _patch_voice_config(_FakeVoiceConfig()),
            patch("websockets.connect", side_effect=ConnectionRefusedError("refused")),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))

                msg = ws.receive_text()
                data = json.loads(msg)
                assert data["type"] == "error"
                assert "STT connection failed" in data["message"]

    def test_streaming_stt_with_keyterms(self, client: TestClient) -> None:
        dg_response = json.dumps(
            {
                "type": "Results",
                "is_final": True,
                "channel": {"alternatives": [{"transcript": "test keyword"}]},
            }
        )
        fake_dg = _FakeDgWs(responses=[dg_response])

        with (
            _patch_voice_config(_FakeVoiceConfig()),
            patch("websockets.connect", return_value=fake_dg),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(
                    json.dumps(
                        {
                            "type": "config",
                            "keyterms": ["keyword1", " ", "keyword2"],
                        }
                    )
                )

                msg = ws.receive_text()
                data = json.loads(msg)
                assert data["type"] == "stt_final"

                ws.send_text(json.dumps({"type": "close"}))

    def test_streaming_stt_no_language(self, client: TestClient) -> None:
        fake_dg = _FakeDgWs(responses=[])
        config = _FakeVoiceConfig(stt_language=None)

        with (
            _patch_voice_config(config),
            patch("websockets.connect", return_value=fake_dg),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.send_text(json.dumps({"type": "close"}))

    def test_streaming_audio_forwarded_to_deepgram(self, client: TestClient) -> None:
        """Audio bytes sent during streaming mode reach the Deepgram WS."""
        fake_dg = _FakeDgWs(responses=[], hang_after_responses=True)

        with (
            _patch_voice_config(_FakeVoiceConfig()),
            patch("websockets.connect", return_value=fake_dg),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.send_bytes(b"\xaa" * 256)
                ws.send_bytes(b"\xbb" * 512)
                ws.send_text(json.dumps({"type": "close"}))

        audio_chunks = [s for s in fake_dg._sent if isinstance(s, bytes)]
        assert len(audio_chunks) == 2
        assert audio_chunks[0] == b"\xaa" * 256
        assert audio_chunks[1] == b"\xbb" * 512

    def test_streaming_text_messages_handled(self, client: TestClient) -> None:
        """Control messages during streaming are dispatched correctly."""
        fake_dg = _FakeDgWs(responses=[], hang_after_responses=True)

        with (
            _patch_voice_config(_FakeVoiceConfig()),
            patch("websockets.connect", return_value=fake_dg),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.send_text(json.dumps({"type": "tts", "text": "speak this"}))
                ws.send_text(json.dumps({"type": "close"}))

    def test_streaming_oversized_audio_dropped(self, client: TestClient) -> None:
        fake_dg = _FakeDgWs(responses=[], hang_after_responses=True)

        with (
            _patch_voice_config(_FakeVoiceConfig()),
            patch("websockets.connect", return_value=fake_dg),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.send_bytes(b"\x00" * (1024 * 1024 + 1))
                ws.send_text(json.dumps({"type": "close"}))

        audio_chunks = [s for s in fake_dg._sent if isinstance(s, bytes)]
        assert len(audio_chunks) == 0


class TestTTSFlow:
    """Tests for TTS request and cancel (barge-in) flow."""

    def test_tts_request_triggers_synthesis(self, client: TestClient) -> None:
        chunks_sent: list[bytes] = []

        async def fake_synthesize_stream(text: str, config: object) -> AsyncIterator[bytes]:
            for i in range(3):
                chunk = f"audio_chunk_{i}".encode()
                chunks_sent.append(chunk)
                yield chunk

        with (
            _patch_voice_config(_FakeVoiceConfig(stt_provider="openai")),
            patch(
                "app.api.voice.ws_session._VoiceSession._run_batch_stt",
                new_callable=AsyncMock,
            ) as mock_batch,
        ):
            mock_batch.return_value = None

            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config", "keyterms": []}))

                with patch(
                    "app.channels.voice.tts.synthesize_stream",
                    side_effect=fake_synthesize_stream,
                ):
                    ws.send_text(json.dumps({"type": "tts", "text": "Hello world"}))
                    ws.send_text(json.dumps({"type": "close"}))

    def test_tts_cancel_interrupts(self, client: TestClient) -> None:
        async def slow_synthesize(text: str, config: object) -> AsyncIterator[bytes]:
            for i in range(100):
                yield f"chunk_{i}".encode()
                await asyncio.sleep(0.01)

        with (
            _patch_voice_config(_FakeVoiceConfig(stt_provider="openai")),
            patch(
                "app.api.voice.ws_session._VoiceSession._run_batch_stt",
                new_callable=AsyncMock,
            ),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))

                with patch(
                    "app.channels.voice.tts.synthesize_stream",
                    side_effect=slow_synthesize,
                ):
                    ws.send_text(json.dumps({"type": "tts", "text": "Long text"}))
                    ws.send_text(json.dumps({"type": "tts_cancel"}))
                    ws.send_text(json.dumps({"type": "close"}))

    def test_tts_synthesis_error_handled(self, client: TestClient) -> None:
        async def failing_synthesize(text: str, config: object) -> AsyncIterator[bytes]:
            raise RuntimeError("TTS provider error")
            yield b""  # type: ignore[misc]

        with (
            _patch_voice_config(_FakeVoiceConfig(stt_provider="openai")),
            patch(
                "app.api.voice.ws_session._VoiceSession._run_batch_stt",
                new_callable=AsyncMock,
            ),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))

                with patch(
                    "app.channels.voice.tts.synthesize_stream",
                    side_effect=failing_synthesize,
                ):
                    ws.send_text(json.dumps({"type": "tts", "text": "Test"}))
                    ws.send_text(json.dumps({"type": "close"}))


class TestBatchSTTFallback:
    """Tests for non-streaming STT provider fallback to batch mode."""

    def test_batch_provider_sends_info_message(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfigBatch()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))

                msg = ws.receive_text()
                data = json.loads(msg)
                assert data["type"] == "info"
                assert data["message"] == "streaming_unavailable"
                assert data["fallback"] == "batch"

                ws.send_text(json.dumps({"type": "close"}))

    def test_batch_stt_with_audio_then_end_utterance(self, client: TestClient) -> None:
        async def fake_transcribe(path: object, config: object) -> MagicMock:
            result = MagicMock()
            result.text = "transcribed text"
            return result

        with (
            _patch_voice_config(_FakeVoiceConfigBatch()),
            patch(
                "app.channels.voice.stt.transcribe",
                side_effect=fake_transcribe,
            ),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.receive_text()

                ws.send_bytes(b"\x00" * 2048)
                ws.send_text(json.dumps({"type": "end_utterance"}))

                msg = ws.receive_text()
                data = json.loads(msg)
                assert data["type"] == "stt_final"
                assert data["text"] == "transcribed text"

                ws.send_text(json.dumps({"type": "close"}))

    def test_batch_stt_too_short_audio_skipped(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfigBatch()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.receive_text()

                ws.send_bytes(b"\x00" * 100)
                ws.send_text(json.dumps({"type": "end_utterance"}))

                ws.send_text(json.dumps({"type": "close"}))

    def test_batch_stt_audio_too_large_rejected(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfigBatch()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.receive_text()

                for _ in range(26):
                    ws.send_bytes(b"\x00" * (1024 * 1024))

    def test_batch_transcribe_failure_handled(self, client: TestClient) -> None:
        async def failing_transcribe(path: object, config: object) -> None:
            raise RuntimeError("STT provider error")

        with (
            _patch_voice_config(_FakeVoiceConfigBatch()),
            patch(
                "app.channels.voice.stt.transcribe",
                side_effect=failing_transcribe,
            ),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.receive_text()

                ws.send_bytes(b"\x00" * 2048)
                ws.send_text(json.dumps({"type": "end_utterance"}))

                ws.send_text(json.dumps({"type": "close"}))


class TestControlMessages:
    """Tests for control message handling."""

    def test_close_message_ends_session(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfigBatch()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.receive_text()
                ws.send_text(json.dumps({"type": "close"}))

    def test_empty_tts_text_ignored(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfigBatch()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.receive_text()
                ws.send_text(json.dumps({"type": "tts", "text": "  "}))
                ws.send_text(json.dumps({"type": "close"}))

    def test_malformed_json_ignored(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfigBatch()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.receive_text()
                ws.send_text("not json at all")
                ws.send_text(json.dumps({"type": "close"}))

    def test_unknown_message_type_ignored(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfigBatch()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.receive_text()
                ws.send_text(json.dumps({"type": "unknown_type"}))
                ws.send_text(json.dumps({"type": "close"}))


class TestAudioChunkHandling:
    """Tests for binary audio data forwarding."""

    def test_oversized_audio_chunk_dropped(self, client: TestClient) -> None:
        with _patch_voice_config(_FakeVoiceConfigBatch()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.receive_text()
                ws.send_bytes(b"\x00" * (1024 * 1024 + 1))
                ws.send_text(json.dumps({"type": "close"}))

    def test_valid_audio_chunk_forwarded_in_batch(self, client: TestClient) -> None:
        """In batch mode, valid audio chunks are collected (not dropped)."""
        with _patch_voice_config(_FakeVoiceConfigBatch()):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.receive_text()
                ws.send_bytes(b"\x00" * 2048)
                ws.send_text(json.dumps({"type": "close"}))


class TestLoadVoiceConfig:
    """Tests for the _load_voice_config helper."""

    def test_load_voice_config_returns_config(self, client: TestClient) -> None:
        fake_config = _FakeVoiceConfig()

        with (
            patch("app.config.deploy_mode.is_sandbox", return_value=False),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
            ) as mock_load,
            patch(
                "app.core.channel_bridge.config_parsers.extract_voice_config",
                return_value=fake_config,
            ),
        ):
            mock_load.return_value = MagicMock(voice_dict={})

            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                ws.send_text(json.dumps({"type": "close"}))

    def test_load_voice_config_stt_disabled(self, client: TestClient) -> None:
        disabled_config = _FakeVoiceConfigDisabled()

        with (
            patch("app.config.deploy_mode.is_sandbox", return_value=False),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
            ) as mock_load,
            patch(
                "app.core.channel_bridge.config_parsers.extract_voice_config",
                return_value=disabled_config,
            ),
        ):
            mock_load.return_value = MagicMock(voice_dict={})

            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))

    def test_load_voice_config_exception_handled(self, client: TestClient) -> None:
        with (
            patch("app.config.deploy_mode.is_sandbox", return_value=False),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                side_effect=RuntimeError("config db error"),
            ),
        ):
            with client.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))

    def test_load_voice_config_sandbox_no_user_id(self) -> None:
        """In sandbox mode without user_id, auth error is returned."""
        app = _make_app()
        tc = TestClient(app)
        caps = MagicMock(requires_strict_ws_auth=True)
        with (
            patch("app.api.voice.ws_session.verify_ws_origin", new_callable=AsyncMock, return_value=True),
            patch(
                "app.platform_utils.deployment_capabilities.get_deployment_capabilities",
                return_value=caps,
            ),
        ):
            with tc.websocket_connect("/ws/voice/session") as ws:
                ws.send_text(json.dumps({"type": "config"}))
                payload = json.loads(ws.receive_text())
                assert payload["type"] == "error"
                assert payload["message"] == "Authentication required"


class TestSendJsonRobustness:
    """Tests for _send_json and _send_json_to_ws error handling."""

    @pytest.mark.asyncio
    async def test_send_json_skips_when_closed(self) -> None:
        """_send_json should not attempt to send when session is closed."""
        ws_mock = AsyncMock()
        config = _FakeVoiceConfig()
        session = _VoiceSession(ws=ws_mock, voice_config=config, keyterms=[])
        session._closed = True
        await session._send_json({"type": "test"})
        ws_mock.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_json_handles_disconnect(self) -> None:
        """_send_json sets _closed on WebSocketDisconnect."""
        ws_mock = AsyncMock()
        ws_mock.send_text.side_effect = WebSocketDisconnect()
        config = _FakeVoiceConfig()
        session = _VoiceSession(ws=ws_mock, voice_config=config, keyterms=[])
        await session._send_json({"type": "test"})
        assert session._closed is True

    @pytest.mark.asyncio
    async def test_send_json_to_ws_handles_runtime_error(self) -> None:
        """_send_json_to_ws swallows RuntimeError."""
        ws_mock = AsyncMock()
        ws_mock.send_text.side_effect = RuntimeError("connection closed")
        await _send_json_to_ws(ws_mock, {"type": "error", "message": "test"})

    @pytest.mark.asyncio
    async def test_send_json_to_ws_handles_disconnect(self) -> None:
        """_send_json_to_ws swallows WebSocketDisconnect."""
        ws_mock = AsyncMock()
        ws_mock.send_text.side_effect = WebSocketDisconnect()
        await _send_json_to_ws(ws_mock, {"type": "error", "message": "test"})

    @pytest.mark.asyncio
    async def test_close_ws_handles_exception(self) -> None:
        """_close_ws swallows exceptions on close."""
        ws_mock = AsyncMock()
        ws_mock.close.side_effect = RuntimeError("already closed")
        await _close_ws(ws_mock, 1000, "test")
