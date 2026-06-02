"""Tests for GET /chats/{chat_id}/export — toolSummary + usageSummary."""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport

from app.main import app


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


async def _create_chat_with_messages(
    chat_id: str,
    *,
    total_calls: int = 5,
    total_tokens: int = 1000,
    total_usd: float = 0.05,
) -> None:
    """Insert a chat + messages directly into DB for testing."""
    from datetime import datetime, timezone

    from app.database.models.chat import Chat, Message
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(
            id=chat_id,
            title="Export Test Chat",
            action_mode="fast",
            source="web",
            total_calls=total_calls,
            total_tokens=total_tokens,
            total_usd=total_usd,
        )
        db.add(chat)

        now = datetime.now(tz=timezone.utc)
        db.add(
            Message(
                id=f"msg-user-{uuid.uuid4().hex[:8]}",
                chat_id=chat_id,
                role="user",
                content="Hello, can you help me?",
                sent_at=now,
                sent_timezone="UTC",
            )
        )
        db.add(
            Message(
                id=f"msg-asst-{uuid.uuid4().hex[:8]}",
                chat_id=chat_id,
                role="assistant",
                content="Sure, I can help you with that.",
                sent_at=now,
                sent_timezone="UTC",
            )
        )
        await db.commit()


async def _create_tool_events(chat_id: str) -> None:
    """Insert AgentTurn + AgentEvent records for tool call testing."""
    from app.database.models.agent_event import AgentEvent, AgentTurn
    from app.platform_utils import get_session_factory
    from app.services.event.types import EventType

    turn_id = f"turn-{uuid.uuid4().hex[:8]}"

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            AgentTurn(
                id=turn_id,
                chat_id=chat_id,
                turn_index=0,
                status="completed",
            )
        )
        await db.flush()

        db.add(
            AgentEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                turn_id=turn_id,
                event_type=EventType.TOOL_CALL_END.value,
                level="info",
                event_index=0,
                payload={"output": {}, "success": True},
                tool_name="web_search",
                duration_ms=1200,
            )
        )
        db.add(
            AgentEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                turn_id=turn_id,
                event_type=EventType.TOOL_CALL_END.value,
                level="info",
                event_index=1,
                payload={"output": {}, "success": True},
                tool_name="web_search",
                duration_ms=800,
            )
        )
        db.add(
            AgentEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                turn_id=turn_id,
                event_type=EventType.TOOL_CALL_END.value,
                level="info",
                event_index=2,
                payload={"output": {}, "success": True},
                tool_name="file_read",
                duration_ms=50,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_export_chat_returns_usage_summary(
    async_client: httpx.AsyncClient,
) -> None:
    """Export endpoint includes usageSummary from Chat table fields."""
    chat_id = f"test-export-usage-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id, total_calls=10, total_tokens=5000, total_usd=0.12)

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    data = res.json()["data"]
    usage = data["usageSummary"]
    assert usage["totalCalls"] == 10
    assert usage["totalTokens"] == 5000
    assert usage["totalUsd"] == pytest.approx(0.12, abs=0.001)


@pytest.mark.asyncio
async def test_export_chat_returns_tool_summary(
    async_client: httpx.AsyncClient,
) -> None:
    """Export endpoint aggregates tool calls from AgentTurn/AgentEvent."""
    chat_id = f"test-export-tools-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)
    await _create_tool_events(chat_id)

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    data = res.json()["data"]
    tool_summary = data["toolSummary"]
    assert tool_summary is not None
    assert tool_summary["totalToolCalls"] == 3
    assert tool_summary["totalDurationMs"] == 2050

    tools_used = tool_summary["toolsUsed"]
    assert len(tools_used) == 2
    assert tools_used[0]["name"] == "web_search"
    assert tools_used[0]["count"] == 2
    assert tools_used[0]["totalMs"] == 2000
    assert tools_used[1]["name"] == "file_read"
    assert tools_used[1]["count"] == 1


@pytest.mark.asyncio
async def test_export_chat_tool_summary_null_when_no_turns(
    async_client: httpx.AsyncClient,
) -> None:
    """toolSummary is null when no AgentTurn data exists (e.g. SaaS mode)."""
    chat_id = f"test-export-no-turns-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    data = res.json()["data"]
    assert data["toolSummary"] is None


@pytest.mark.asyncio
async def test_export_chat_includes_messages(
    async_client: httpx.AsyncClient,
) -> None:
    """Export includes filtered messages (user + assistant only)."""
    chat_id = f"test-export-msgs-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    data = res.json()["data"]
    messages = data["messages"]
    assert len(messages) == 2
    roles = {m["role"] for m in messages}
    assert roles == {"user", "assistant"}


@pytest.mark.asyncio
async def test_export_chat_not_found(
    async_client: httpx.AsyncClient,
) -> None:
    """Export returns 404 for non-existent chat."""
    res = await async_client.get("/api/v1/chats/non-existent-chat-id/export")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_export_chat_metadata(
    async_client: httpx.AsyncClient,
) -> None:
    """Export includes chat metadata (id, title, source, createdAt)."""
    chat_id = f"test-export-meta-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    chat_data = res.json()["data"]["chat"]
    assert chat_data["id"] == chat_id
    assert chat_data["title"] == "Export Test Chat"
    assert chat_data["source"] == "web"
    assert "createdAt" in chat_data


@pytest.mark.asyncio
async def test_export_tool_summary_null_when_turns_exist_but_no_tool_events(
    async_client: httpx.AsyncClient,
) -> None:
    """toolSummary is None when turns exist but contain no tool_call_end events."""
    from app.database.models.agent_event import AgentTurn
    from app.platform_utils import get_session_factory

    chat_id = f"test-export-notool-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            AgentTurn(
                id=f"turn-empty-{uuid.uuid4().hex[:8]}",
                chat_id=chat_id,
                turn_index=0,
                status="completed",
            )
        )
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["toolSummary"] is None


@pytest.mark.asyncio
async def test_export_tool_summary_handles_null_duration(
    async_client: httpx.AsyncClient,
) -> None:
    """duration_ms=None in AgentEvent is treated as 0."""
    from app.database.models.agent_event import AgentEvent, AgentTurn
    from app.platform_utils import get_session_factory
    from app.services.event.types import EventType

    chat_id = f"test-export-nulldur-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    turn_id = f"turn-{uuid.uuid4().hex[:8]}"
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(AgentTurn(id=turn_id, chat_id=chat_id, turn_index=0, status="completed"))
        await db.flush()
        db.add(
            AgentEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                turn_id=turn_id,
                event_type=EventType.TOOL_CALL_END.value,
                level="info",
                event_index=0,
                payload={"output": {}, "success": True},
                tool_name="web_search",
                duration_ms=None,
            )
        )
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    ts = res.json()["data"]["toolSummary"]
    assert ts is not None
    assert ts["totalToolCalls"] == 1
    assert ts["totalDurationMs"] == 0
    assert ts["toolsUsed"][0]["totalMs"] == 0


@pytest.mark.asyncio
async def test_export_aggregates_across_multiple_turns(
    async_client: httpx.AsyncClient,
) -> None:
    """Tool calls from multiple turns are aggregated correctly."""
    from app.database.models.agent_event import AgentEvent, AgentTurn
    from app.platform_utils import get_session_factory
    from app.services.event.types import EventType

    chat_id = f"test-export-multi-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    session_factory = get_session_factory()
    async with session_factory() as db:
        turn1_id = f"turn-1-{uuid.uuid4().hex[:8]}"
        turn2_id = f"turn-2-{uuid.uuid4().hex[:8]}"
        db.add(AgentTurn(id=turn1_id, chat_id=chat_id, turn_index=0, status="completed"))
        db.add(AgentTurn(id=turn2_id, chat_id=chat_id, turn_index=1, status="completed"))
        await db.flush()

        db.add(
            AgentEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                turn_id=turn1_id,
                event_type=EventType.TOOL_CALL_END.value,
                level="info",
                event_index=0,
                payload={},
                tool_name="web_search",
                duration_ms=500,
            )
        )
        db.add(
            AgentEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                turn_id=turn2_id,
                event_type=EventType.TOOL_CALL_END.value,
                level="info",
                event_index=0,
                payload={},
                tool_name="web_search",
                duration_ms=300,
            )
        )
        db.add(
            AgentEvent(
                id=f"evt-{uuid.uuid4().hex[:8]}",
                turn_id=turn2_id,
                event_type=EventType.TOOL_CALL_END.value,
                level="info",
                event_index=1,
                payload={},
                tool_name="code_exec",
                duration_ms=1000,
            )
        )
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    ts = res.json()["data"]["toolSummary"]
    assert ts["totalToolCalls"] == 3
    assert ts["totalDurationMs"] == 1800
    assert ts["toolsUsed"][0]["name"] == "web_search"
    assert ts["toolsUsed"][0]["count"] == 2
    assert ts["toolsUsed"][0]["totalMs"] == 800


@pytest.mark.asyncio
async def test_export_empty_chat_no_messages(
    async_client: httpx.AsyncClient,
) -> None:
    """Chat with no messages returns empty messages list."""
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    chat_id = f"test-export-empty-{uuid.uuid4().hex[:8]}"
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(Chat(id=chat_id, title="Empty Chat", action_mode="fast", source="web"))
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    data = res.json()["data"]
    assert data["messages"] == []
    assert data["chat"]["id"] == chat_id
    assert data["usageSummary"]["totalCalls"] == 0


@pytest.mark.asyncio
async def test_export_zero_usage_summary(
    async_client: httpx.AsyncClient,
) -> None:
    """usageSummary with all zeros is returned correctly."""
    chat_id = f"test-export-zero-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id, total_calls=0, total_tokens=0, total_usd=0.0)

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    usage = res.json()["data"]["usageSummary"]
    assert usage["totalCalls"] == 0
    assert usage["totalTokens"] == 0
    assert usage["totalUsd"] == 0.0
