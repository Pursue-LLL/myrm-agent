"""Integration test: _inject_wu_consumed in stream_lane_factory MESSAGE_END chain.

Tests both the unit function and the real SSE EVENT chain via HTTP API.
"""

from __future__ import annotations

import json
import os

import pytest
import requests

from tests.support.test_secrets import load_test_secrets

_secrets = load_test_secrets()
_HAS_LLM = _secrets.has_basic_credentials
_SERVER_BASE = os.getenv("MYRM_SERVER_URL", "http://localhost:8080")



def _stream_sse_events(query: str) -> list[dict]:
    """Send a message to the live server via SSE and collect events."""
    import uuid

    payload = {
        "message_id": f"msg-wu-{uuid.uuid4().hex[:8]}",
        "chat_id": f"chat-wu-{os.getpid()}",
        "query": query,
    }
    resp = requests.post(
        f"{_SERVER_BASE}/api/v1/agents/agent-stream",
        json=payload,
        stream=True,
        timeout=120,
    )
    resp.raise_for_status()

    events: list[dict] = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if raw == "[DONE]":
            break
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return events


@pytest.mark.integration
@pytest.mark.skipif(not _HAS_LLM, reason="BASIC_MODEL credentials not available")
def test_live_message_end_sse_chain() -> None:
    """Real HTTP SSE: MESSAGE_END fields and wu_consumed absence in tauri mode.

    Verifies:
    1. The SSE stream produces a valid message_end with completion_status=complete
    2. cost_usd is present if token_usage events reported cost > 0
    3. wu_consumed is NOT injected in tauri mode (only in sandbox)
    4. usage/token_economics fields are present
    """
    events = _stream_sse_events("Say exactly: 'hi'")

    message_ends = [e for e in events if e.get("type") == "message_end"]
    assert message_ends, f"No message_end event found. Events: {[e.get('type') for e in events]}"
    end = message_ends[-1]

    assert end.get("completion_status") == "complete", f"Unexpected status: {end.get('completion_status')}"

    # Check if token_usage events reported cost
    token_usages = [e for e in events if e.get("type") == "token_usage"]
    has_cost = any(
        isinstance(e.get("data", {}).get("cost_usd"), (int, float))
        and e["data"]["cost_usd"] > 0
        for e in token_usages
        if isinstance(e.get("data"), dict)
    )

    if has_cost:
        assert "cost_usd" in end, f"cost_usd missing despite token_usage reporting cost. Keys: {list(end.keys())}"
        assert isinstance(end["cost_usd"], (int, float))
        assert end["cost_usd"] > 0

    # In tauri mode, wu_consumed should NEVER be present
    assert "wu_consumed" not in end, (
        "wu_consumed should NOT be injected in tauri mode (only in sandbox)"
    )

    # usage or token_economics must be present
    assert "usage" in end or "token_economics" in end, (
        f"Neither 'usage' nor 'token_economics' in MESSAGE_END: {list(end.keys())}"
    )


@pytest.mark.integration
@pytest.mark.skipif(not _HAS_LLM, reason="BASIC_MODEL credentials not available")
def test_live_message_end_has_usage_field() -> None:
    """Real HTTP SSE: MESSAGE_END should include usage (token counts)."""
    events = _stream_sse_events("Say exactly: 'hello'")

    message_ends = [e for e in events if e.get("type") == "message_end"]
    assert message_ends, "No message_end found"
    end = message_ends[-1]

    assert "usage" in end or "token_economics" in end, (
        f"Neither 'usage' nor 'token_economics' in MESSAGE_END: {list(end.keys())}"
    )
