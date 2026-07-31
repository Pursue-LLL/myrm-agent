"""WebSocket STT stream guard when optional local-stt extra is missing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.features import _reset_for_testing

from app.api.stt import ws_stream
from app.channels.types import VoiceConfig
from tests.support.feature_flags import seed_voice_interaction_flags


def _local_voice() -> VoiceConfig:
    return VoiceConfig(stt_enabled=True, stt_provider="local")


@pytest.fixture
def ws_client() -> TestClient:
    seed_voice_interaction_flags()
    app = FastAPI()
    app.include_router(ws_stream.router, prefix="/ws/stt")
    with TestClient(app) as client:
        yield client
    _reset_for_testing()


def test_ws_stream_returns_error_when_local_stt_unavailable(ws_client: TestClient) -> None:
    with (
        patch.object(ws_stream, "verify_ws_origin", new_callable=AsyncMock, return_value=True),
        patch.object(
            ws_stream,
            "_load_voice_config_from_ws",
            new_callable=AsyncMock,
            return_value=_local_voice(),
        ),
        patch("app.channels.voice.stt.is_local_available", return_value=False),
    ):
        with ws_client.websocket_connect("/ws/stt/stream") as ws:
            ws.send_json({"keyterms": []})
            payload = ws.receive_json()

    assert payload["type"] == "error"
    assert "local-stt" in str(payload["message"])
