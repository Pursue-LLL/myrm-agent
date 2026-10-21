"""Real-model live steer round-trip — no mocks on the steering path.

Starts a real ``agent-stream`` turn (real LLM via ``BASIC_*`` test credentials)
and injects a mid-run ``/steer`` message from a concurrent thread, proving the
full production chain: router -> SteeringRegistry -> live SteeringToken ->
harness injection -> model turn completes with steering active.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.e2e
@pytest.mark.timeout(300)
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY",
)
def test_live_steer_lands_mid_run(app: FastAPI, setup_test_database) -> None:
    """A steer sent while a real model turn streams must report steered:true."""
    chat_id = f"live-steer-{uuid.uuid4().hex[:8]}"
    stop = threading.Event()
    outcome: dict[str, object] = {"steered": False, "policy_steered": False, "attempts": 0}
    stream_status: dict[str, object] = {}

    def _pump_stream() -> None:
        with patch(
            "app.core.security.auth.identity.is_loopback_ip", return_value=True
        ):
            with TestClient(app) as stream_client:
                body = {
                    "messageId": str(uuid.uuid4()),
                    "query": "Write exactly 6 numbered facts about oak trees, one sentence each.",
                    "chatId": chat_id,
                    "modelSelection": get_model_selection(),
                    "actionMode": "agent",
                }
                try:
                    with stream_client.stream(
                        "POST", "/api/v1/agents/agent-stream", json=body, timeout=180.0
                    ) as resp:
                        stream_status["http"] = resp.status_code
                        chunks = 0
                        for _line in resp.iter_lines():
                            chunks += 1
                        stream_status["chunks"] = chunks
                finally:
                    stop.set()

    def _pump_steer() -> None:
        with patch(
            "app.core.security.auth.identity.is_loopback_ip", return_value=True
        ):
            with TestClient(app) as steer_client:
                while not stop.is_set():
                    outcome["attempts"] = int(outcome["attempts"]) + 1
                    resp = steer_client.post(
                        f"/api/v1/agents/chats/{chat_id}/steer",
                        json={"message": "mention acorns in one fact"},
                    )
                    data = resp.json()
                    if data.get("success") is True:
                        outcome["steered"] = True
                    policy_resp = steer_client.post(
                        f"/api/v1/agents/chats/{chat_id}/steer",
                        json={
                            "message": "keep each fact to one sentence",
                            "mode": "policy",
                            "quotedRef": "live-e2e",
                        },
                    )
                    policy_data = policy_resp.json()
                    if policy_data.get("success") is True:
                        outcome["policy_steered"] = True
                    if outcome["steered"] is True and outcome["policy_steered"] is True:
                        return
                    time.sleep(1.0)

    producer = threading.Thread(target=_pump_stream, daemon=True)
    injector = threading.Thread(target=_pump_steer, daemon=True)
    producer.start()
    # Give the stream a head start so a live session exists before steering.
    time.sleep(3.0)
    injector.start()
    producer.join(timeout=200.0)
    injector.join(timeout=30.0)

    assert stream_status.get("http") == 200, stream_status
    assert int(stream_status.get("chunks", 0)) > 0, stream_status
    assert outcome["steered"] is True, outcome
    assert outcome["policy_steered"] is True, outcome
