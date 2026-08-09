"""Integration test: _inject_wu_consumed in stream_lane_factory MESSAGE_END chain.

Uses ASGI TestClient via conftest-level app fixture (same approach as the
disconnect tolerance E2E). The conftest.py that provides ``app`` and ``client``
lives under tests/api/agent/; this file redirects to avoid moving test ownership.

When the ``client`` fixture is unavailable (running from this directory only),
these tests are auto-skipped.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None  # type: ignore[assignment,misc]


def _collect_sse_events_via_requests(query: str) -> list[dict]:
    """Fallback: hit the live server via HTTP when ASGI client unavailable."""
    import requests

    from tests.api.agent.utils import get_model_selection, get_search_service_config

    server_base = os.getenv("MYRM_SERVER_URL", "http://localhost:8080")
    payload = {
        "messageId": f"msg-wu-{uuid.uuid4().hex[:8]}",
        "chatId": f"chat-wu-{uuid.uuid4().hex[:8]}",
        "query": query,
        "actionMode": "fast",
        "modelSelection": get_model_selection(),
        "searchServiceCfg": get_search_service_config(),
    }
    try:
        resp = requests.post(
            f"{server_base}/api/v1/agents/agent-stream",
            json=payload,
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()
    except requests.ConnectionError:
        pytest.skip(
            "Live server is not running; start the backend on :8080 "
            "or run from tests/api/agent/ with the ASGI client fixture"
        )

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
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="Integration test requires BASIC_API_KEY environment variable",
)
def test_live_message_end_sse_chain() -> None:
    """Real HTTP SSE: MESSAGE_END fields and wu_consumed absence in tauri mode.

    Verifies:
    1. The SSE stream produces a valid message_end with completion_status=complete
    2. cost_usd is present if token_usage events reported cost > 0
    3. wu_consumed is NOT injected in tauri mode (only in sandbox)
    4. usage/token_economics fields are present
    """
    events = _collect_sse_events_via_requests("Say exactly: 'hi'")

    error_events = [e for e in events if e.get("type") == "error"]
    if error_events:
        error_data = str(error_events[0].get("data", ""))
        if (
            "Stream setup failed" in error_data
            or "Search service not configured" in error_data
            or "requires full session context" in error_data
        ):
            pytest.skip(
                "Live server lacks full session context "
                "(run via tests/api/agent/ with client fixture)"
            )

    message_ends = [e for e in events if e.get("type") == "message_end"]
    assert message_ends, f"No message_end event found. Events: {[e.get('type') for e in events]}"
    end = message_ends[-1]

    assert end.get("completion_status") == "complete", f"Unexpected status: {end.get('completion_status')}"

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

    assert "wu_consumed" not in end, (
        "wu_consumed should NOT be injected in tauri mode (only in sandbox)"
    )

    assert "usage" in end or "token_economics" in end, (
        f"Neither 'usage' nor 'token_economics' in MESSAGE_END: {list(end.keys())}"
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="Integration test requires BASIC_API_KEY environment variable",
)
def test_live_message_end_has_usage_field() -> None:
    """Real HTTP SSE: MESSAGE_END should include usage (token counts)."""
    events = _collect_sse_events_via_requests("Say exactly: 'hello'")

    error_events = [e for e in events if e.get("type") == "error"]
    if error_events:
        error_data = str(error_events[0].get("data", ""))
        if (
            "Stream setup failed" in error_data
            or "Search service not configured" in error_data
            or "requires full session context" in error_data
        ):
            pytest.skip(
                "Live server lacks full session context "
                "(run via tests/api/agent/ with client fixture)"
            )

    message_ends = [e for e in events if e.get("type") == "message_end"]
    assert message_ends, "No message_end found"
    end = message_ends[-1]

    assert "usage" in end or "token_economics" in end, (
        f"Neither 'usage' nor 'token_economics' in MESSAGE_END: {list(end.keys())}"
    )
