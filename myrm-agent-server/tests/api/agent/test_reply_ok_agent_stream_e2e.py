"""Live-server API E2E: agent-stream SSE for minimal reply prompt.

Complements Chrome mux MCP UI tests where long SSE streams exceed MCP upstream timeouts.
Hits the running dev server at :8080 (same stack as Chrome E2E).
"""

from __future__ import annotations

import json
import os
import re
import uuid

import httpx
import pytest

from tests.api.agent.utils import check_e2e_errors

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8080")
_E2E_TIMEOUT = httpx.Timeout(180.0)
E2E_PROMPT = "只回复 OK"
_OK_PATTERN = re.compile(r"\bOK\b", re.IGNORECASE)

_skip_live = pytest.mark.skipif(
    not os.getenv("RUN_E2E_TESTS"),
    reason="Set RUN_E2E_TESTS=1 to run against live server at :8080",
)


def _message_text(events: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        if event.get("type") != "message":
            continue
        data = event.get("data")
        if isinstance(data, str) and data:
            chunks.append(data)
    return "".join(chunks)


def _collect_agent_stream(payload: dict[str, object]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    with httpx.Client(trust_env=False, timeout=_E2E_TIMEOUT) as client:
        with client.stream(
            "POST",
            f"{BASE_URL}/api/v1/agents/agent-stream",
            json=payload,
            headers={"Accept": "text/event-stream"},
        ) as response:
            if response.status_code != 200:
                body = response.read().decode("utf-8", errors="replace")
                pytest.fail(f"agent-stream HTTP {response.status_code}: {body[:500]}")
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    break
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    events.append(parsed)
    return events


def _live_server_ready() -> bool:
    try:
        with httpx.Client(trust_env=False, timeout=httpx.Timeout(5.0)) as client:
            response = client.get(f"{BASE_URL}/health")
            return response.status_code == 200
    except httpx.HTTPError:
        return False


@_skip_live
@pytest.mark.e2e
def test_live_agent_stream_reply_ok_sse() -> None:
    """Live POST /api/v1/agents/agent-stream must finish with an OK assistant reply."""
    if not _live_server_ready():
        pytest.skip(f"Live server not reachable at {BASE_URL}")

    raw_model = os.environ.get("BASIC_MODEL") or os.environ.get("LITE_MODEL")
    if not raw_model:
        pytest.skip("BASIC_MODEL or LITE_MODEL required in .env.test")

    provider_id = raw_model.split("/")[0] if "/" in raw_model else "minimax"
    model = raw_model.split("/", 1)[1] if "/" in raw_model else raw_model
    if provider_id == "openai-like":
        provider_id = "openai-like"
    base_url = os.environ.get("BASIC_BASE_URL") or os.environ.get("LITE_BASE_URL")

    chat_id = f"test_reply_ok_{uuid.uuid4().hex[:10]}"
    with httpx.Client(trust_env=False, timeout=_E2E_TIMEOUT) as client:
        create = client.post(f"{BASE_URL}/api/v1/chats/", json={"chat_id": chat_id})
        assert create.status_code == 200, create.text

    payload: dict[str, object] = {
        "message_id": f"msg_{uuid.uuid4().hex[:10]}",
        "chat_id": chat_id,
        "query": E2E_PROMPT,
        "model_selection": {
            "providerId": provider_id,
            "model": model,
            "baseUrl": base_url,
        },
        "action_mode": "agent",
        "enable_memory": False,
    }

    events = _collect_agent_stream(payload)
    check_e2e_errors(events)
    final_text = _message_text(events)
    assert final_text.strip(), (
        f"Expected assistant text in SSE stream; event_types={sorted({e.get('type') for e in events})}"
    )
    assert _OK_PATTERN.search(final_text), f"Expected OK in assistant reply; got={final_text[:200]!r}"
