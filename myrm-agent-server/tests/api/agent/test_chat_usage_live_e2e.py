"""Real-LLM full-turn integration: agent stream persists tokenEconomics into the Chat usage ledger.

Covers the canonical write path (no mocks):
1. ``message_end`` carries ``token_economics`` (collected at stream_collector.py:668)
2. ``stream_finalize`` persists it as ``extra_data.tokenEconomics``
3. ``persist_assistant_message_safe`` triggers ``sync_chat_usage``
4. ``Chat.total_calls/total_tokens/total_usd`` reflect the exact snapshot sum

Requires a real LLM (``@pytest.mark.e2e``) with keys from ``.env.test``.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message
from tests.api.agent.utils import get_model_selection


def _stream_once(
    client: TestClient,
    request_data: dict[str, object],
) -> list[dict]:
    """Stream one agent turn and collect SSE events."""
    collected: list[dict] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data, timeout=120.0) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: "):
                raw = line[6:]
                if raw == "[DONE]":
                    break
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    collected.append(data)
    return collected


async def _assistant_extra_data(db: AsyncSession, chat_id: str) -> list[dict[str, object] | None]:
    rows = await db.execute(
        select(Message.extra_data).where(
            Message.chat_id == chat_id,
            Message.role == "assistant",
        )
    )
    return [dict(row[0]) if row[0] else None for row in rows.all()]


async def _chat_usage(db: AsyncSession, chat_id: str) -> tuple[int, int, float]:
    chat = await db.scalar(select(Chat).where(Chat.id == chat_id))
    assert chat is not None
    return chat.total_calls, chat.total_tokens, chat.total_usd


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
@pytest.mark.asyncio
async def test_real_llm_turn_persists_token_economics_and_aggregates_chat_usage(
    client: TestClient,
    db_session: AsyncSession,
) -> None:
    """A real agent turn leaves an exact usage trail: message extra_data + Chat totals."""
    chat_id = f"usage-live-{uuid.uuid4().hex[:10]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    request_data: dict[str, object] = {
        "messageId": f"usage-live-msg-{uuid.uuid4().hex[:12]}",
        "chatId": chat_id,
        "query": "Reply with the single word: OK",
        "modelSelection": get_model_selection(),
        "actionMode": "chat",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    collected = _stream_once(client, request_data)

    # The stream must have produced at least one message_end with token_economics.
    message_end_events = [d for d in collected if d.get("type") == "message_end"]
    assert message_end_events, "agent-stream must emit message_end for a completed turn"
    token_economics = message_end_events[-1].get("token_economics")
    assert isinstance(token_economics, dict) and token_economics, (
        "message_end must carry token_economics (collected by stream_collector)"
    )

    snapshot: dict[str, object] = dict(token_economics)

    # Persisted message extra_data carries the same snapshot.
    extras = await _assistant_extra_data(db_session, chat_id)
    with_snapshot = [e for e in extras if e and e.get("tokenEconomics")]
    assert with_snapshot, "assistant message extra_data must persist tokenEconomics"
    persisted = with_snapshot[-1]["tokenEconomics"]
    assert isinstance(persisted, dict)
    assert persisted.get("call_count") == snapshot.get("call_count")

    # Chat table totals reflect the aggregated snapshot (exact match, no inflation).
    calls, tokens, usd = await _chat_usage(db_session, chat_id)
    assert calls == int(snapshot.get("call_count", 0))
    assert tokens == int(snapshot.get("usage", {}).get("total_tokens", 0))
    assert abs(usd - float(snapshot.get("total_cost_usd", 0.0))) < 1e-6


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
@pytest.mark.asyncio
async def test_real_llm_two_turns_accumulate_exact_usage(
    client: TestClient,
    db_session: AsyncSession,
) -> None:
    """Two consecutive real turns accumulate exact usage (no loss, no inflation)."""
    chat_id = f"usage-live-2t-{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    def _request(turn: int) -> dict[str, object]:
        return {
            "messageId": f"usage-live-2t-{turn}-{uuid.uuid4().hex[:12]}",
            "chatId": chat_id,
            "query": "Reply with a single word: OK" if turn == 1 else "Now reply with a single word: DONE",
            "modelSelection": get_model_selection(),
            "actionMode": "chat",
            "memoryRequireConfirmation": False,
            "enableMemoryAutoExtraction": False,
        }

    snapshots: list[dict[str, object]] = []
    for turn in (1, 2):
        collected = _stream_once(client, _request(turn))
        message_end_events = [d for d in collected if d.get("type") == "message_end"]
        assert message_end_events, f"turn {turn}: agent-stream must emit message_end"
        token_economics = message_end_events[-1].get("token_economics")
        assert isinstance(token_economics, dict) and token_economics, f"turn {turn}: message_end must carry token_economics"
        snapshots.append(dict(token_economics))

    extras = await _assistant_extra_data(db_session, chat_id)
    with_snapshot = [e for e in extras if e and e.get("tokenEconomics")]
    assert len(with_snapshot) == 2, "two turns must persist two tokenEconomics snapshots"

    expected_calls = sum(int(s.get("call_count", 0)) for s in snapshots)
    expected_tokens = sum(int(s.get("usage", {}).get("total_tokens", 0)) for s in snapshots)
    expected_usd = sum(float(s.get("total_cost_usd", 0.0)) for s in snapshots)

    calls, tokens, usd = await _chat_usage(db_session, chat_id)
    assert calls == expected_calls, f"expected {expected_calls} calls, got {calls}"
    assert tokens == expected_tokens, f"expected {expected_tokens} tokens, got {tokens}"
    assert abs(usd - expected_usd) < 1e-6, f"expected {expected_usd} usd, got {usd}"
