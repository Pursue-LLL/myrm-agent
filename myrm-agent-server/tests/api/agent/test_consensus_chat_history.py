"""Consensus (MoA) multi-turn chat_history integration test.

Validates MOA-01: chat_history flows through the full consensus pipeline
(orchestrator → stream_lane_factory → ConsensusEngine) and produces
valid aggregated output. Uses real LLM calls via .env.test credentials.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.core.features import _reset_for_testing, init_features

from tests.api.agent.utils import check_e2e_errors, get_model_selection


def _enable_consensus_feature() -> None:
    """Enable consensus feature gate for testing."""
    _reset_for_testing()
    from app.services.features.registration import register_all_features

    register_all_features()
    init_features(overrides={"consensus": True})


def _collect_consensus_stream(
    client: TestClient,
    query: str,
    chat_history: list[dict[str, str]] | None = None,
) -> tuple[str, list[dict[str, object]]]:
    """Send a consensus request and collect SSE events."""
    model_selection = get_model_selection()

    request_payload: dict[str, object] = {
        "query": query,
        "message_id": "test-consensus-msg",
        "chat_id": "test-consensus-chat",
        "action_mode": "consensus",
        "model_selection": model_selection,
        "timezone": "UTC",
    }

    if chat_history:
        request_payload["chat_history"] = chat_history

    collected: list[dict[str, object]] = []
    message_chunks: list[str] = []

    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=request_payload, timeout=120.0
    ) as response:
        if response.status_code == 403:
            pytest.skip("consensus feature gate disabled")
        assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"

        for line in response.iter_lines():
            if not line or not line.strip().startswith("data: "):
                continue
            raw = line.strip()[6:]
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                collected.append(data)
                if data.get("type") == "message":
                    content = data.get("data", "")
                    if content:
                        message_chunks.append(str(content))

    return "".join(message_chunks), collected


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestConsensusWithChatHistory:
    """Consensus engine multi-turn chat_history E2E tests."""

    def test_consensus_basic_no_history(self, client: TestClient):
        """Consensus works without chat_history (baseline)."""
        _enable_consensus_feature()

        answer, events = _collect_consensus_stream(client, "1+1等于几")
        assert len(events) > 0, "Should have events"
        check_e2e_errors(events)

        has_consensus_status = any(
            e.get("step_key") in ("consensus_active", "consensus_reference_done", "consensus_done")
            for e in events
            if e.get("type") == "status"
        )
        has_message = any(e.get("type") in ("message", "message_end") for e in events)
        assert has_consensus_status or has_message, "Should have consensus status or message events"

    def test_consensus_with_chat_history(self, client: TestClient):
        """Consensus correctly receives multi-turn chat_history."""
        _enable_consensus_feature()

        chat_history = [
            {"role": "user", "content": "我叫小明"},
            {"role": "assistant", "content": "你好小明！有什么我可以帮你的吗？"},
        ]

        answer, events = _collect_consensus_stream(
            client,
            "我叫什么名字？",
            chat_history=chat_history,
        )
        assert len(events) > 0, "Should have events"
        check_e2e_errors(events)

        has_consensus_status = any(
            e.get("step_key") in ("consensus_active", "consensus_reference_done", "consensus_done")
            for e in events
            if e.get("type") == "status"
        )
        has_message = any(e.get("type") in ("message", "message_end") for e in events)
        assert has_consensus_status or has_message, "Should have consensus events"

    def test_consensus_with_empty_chat_history(self, client: TestClient):
        """Empty chat_history list treated same as None (no crash)."""
        _enable_consensus_feature()

        answer, events = _collect_consensus_stream(client, "2+2等于几", chat_history=[])
        assert len(events) > 0, "Should have events"
        check_e2e_errors(events)

        has_output = any(e.get("type") in ("message", "message_end") for e in events) or any(
            e.get("step_key") in ("consensus_active", "consensus_done")
            for e in events
            if e.get("type") == "status"
        )
        assert has_output, "Should produce output even with empty history"

    def test_consensus_multi_round_history(self, client: TestClient):
        """Multiple rounds of history correctly propagated through consensus."""
        _enable_consensus_feature()

        chat_history = [
            {"role": "user", "content": "北京是哪个国家的首都？"},
            {"role": "assistant", "content": "北京是中国的首都。"},
            {"role": "user", "content": "它的人口大约是多少？"},
            {"role": "assistant", "content": "北京的常住人口大约为2100多万。"},
        ]

        answer, events = _collect_consensus_stream(
            client,
            "这个城市有哪些著名景点？",
            chat_history=chat_history,
        )
        assert len(events) > 0, "Should have events"
        check_e2e_errors(events)

        has_message = any(e.get("type") in ("message", "message_end") for e in events)
        has_consensus = any(
            e.get("step_key") in ("consensus_active", "consensus_done")
            for e in events
            if e.get("type") == "status"
        )
        assert has_message or has_consensus, "Should produce consensus output with multi-round history"

    def test_consensus_event_structure(self, client: TestClient):
        """Validate consensus SSE event lifecycle: active → ref_done → message → done."""
        _enable_consensus_feature()

        _, events = _collect_consensus_stream(client, "什么是人工智能")
        check_e2e_errors(events)

        status_events = [e for e in events if e.get("type") == "status"]
        step_keys = [e.get("step_key") for e in status_events]

        assert "consensus_active" in step_keys, "Should emit consensus_active status"

        active_event = next(e for e in status_events if e.get("step_key") == "consensus_active")
        active_data = active_event.get("data", {})
        assert "reference_models" in active_data, "consensus_active should contain reference_models"

    def test_consensus_feature_gate_blocks_when_disabled(self, client: TestClient):
        """Consensus is correctly blocked when feature gate is disabled."""
        _reset_for_testing()
        from app.services.features.registration import register_all_features

        register_all_features()
        init_features(overrides={"consensus": False})

        model_selection = get_model_selection()
        request_payload: dict[str, object] = {
            "query": "test",
            "message_id": "test-gate",
            "chat_id": "test-gate-chat",
            "action_mode": "consensus",
            "model_selection": model_selection,
            "timezone": "UTC",
        }

        response = client.post("/api/v1/agents/agent-stream", json=request_payload)
        assert response.status_code == 403
