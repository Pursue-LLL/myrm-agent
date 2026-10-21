"""Ensure agent-stream ephemeral memory wrappers never persist into chat_history rows."""

from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app.services.chat.chat_service import ChatService
from tests.api.agent.utils import get_model_selection


def _consume_agent_stream_sse(response) -> tuple[list[dict[str, object]], str]:
    """Parse SSE payloads; concatenate error payloads for diagnostics."""
    events: list[dict[str, object]] = []
    err_parts: list[str] = []

    for line in response.iter_lines():
        if not line or not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        events.append(data)
        if data.get("type") == "error":
            err_parts.append(json.dumps(data, ensure_ascii=False))

    return events, "\n".join(err_parts)


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E requires BASIC_API_KEY for real LiteLLM call",
)
@pytest.mark.asyncio
async def test_load_web_chat_history_excludes_memory_context_markers(
    client: TestClient,
) -> None:
    """Real stream run: DB-visible history must not contain middleware injection wrappers."""
    chat_id = f"mem-persist-{uuid.uuid4().hex[:10]}"
    query_text = (
        "Reply using only ASCII letters: literally the two letters OK "
        "(no punctuation, markdown, explanations, quotes, XML, angle brackets)."
    )

    payload: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "chatId": chat_id,
        "query": query_text,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    forbidden = ("<user_memory_context", "<<<UNTRUSTED_DATA")

    with client.stream(
        "POST",
        "/api/v1/agents/agent-stream",
        json=payload,
        timeout=120.0,
    ) as resp:
        if resp.status_code != 200:
            resp.read()
            pytest.fail(f"Unexpected HTTP status {resp.status_code}: {resp.text}")

        events, joined_errors = _consume_agent_stream_sse(resp)

    fatal_tokens = (
        "Authentication",
        "Authorization",
        "InternalServerError",
        "Cannot connect",
        "Connection error",
    )

    if joined_errors:
        snippet = joined_errors[:500]
        if any(tok in joined_errors for tok in fatal_tokens):
            pytest.skip(f"Environment issue on LLM/stream: {snippet}")
        pytest.fail(f"SSE emitted error payloads: {snippet}")

    hist = await ChatService.load_web_chat_history(chat_id, api_key=None)
    assert hist, "expected chat rows persisted for streamed session"

    message_events = sum(1 for e in events if e.get("type") == "message")
    if message_events == 0:
        pytest.skip("Agent produced no streamed message deltas (possible tool-only path)")

    for entry in hist:
        if len(entry) < 2:
            continue
        role = entry[0]
        body = entry[1]
        if not isinstance(body, str):
            continue
        hit = tuple(m for m in forbidden if m in body)
        assert not hit, f"persisted leakage role={role!r} markers={hit} preview={body[:200]!r}"
