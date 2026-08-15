"""Tests for GET /chats/{chat_id}/export — toolSummary + usageSummary."""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")
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


def _write_event_log(chat_id: str, events: list[dict[str, object]]) -> None:
    """Write harness-style JSONL event-log lines for a chat (agent-event SSOT)."""
    import json
    from pathlib import Path

    from app.config.settings import settings

    log_dir = Path(settings.database.event_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{chat_id}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for seq, event in enumerate(events):
            record = {
                "seq": seq,
                "ts": event["ts"],
                "type": event["type"],
                "sid": chat_id,
                "data": event["data"],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def _create_tool_events(chat_id: str) -> None:
    """Write harness event-log tool activity for tool-call testing."""
    from datetime import datetime, timezone

    base_ts = datetime.now(tz=timezone.utc).timestamp() - 10
    _write_event_log(
        chat_id,
        [
            {"ts": base_ts, "type": "tool_start", "data": {"tool_name": "web_search", "tool_call_id": "call-1", "query": "test"}},
            {"ts": base_ts + 1.2, "type": "tool_end", "data": {"tool_name": "web_search", "tool_call_id": "call-1", "duration_ms": 1200}},
            {"ts": base_ts + 2.0, "type": "tool_start", "data": {"tool_name": "web_search", "tool_call_id": "call-2", "query": "test 2"}},
            {"ts": base_ts + 2.8, "type": "tool_end", "data": {"tool_name": "web_search", "tool_call_id": "call-2", "duration_ms": 800}},
            {"ts": base_ts + 3.0, "type": "tool_start", "data": {"tool_name": "file_read", "tool_call_id": "call-3", "path": "/tmp/x.txt"}},
            {"ts": base_ts + 3.05, "type": "tool_end", "data": {"tool_name": "file_read", "tool_call_id": "call-3", "duration_ms": 50}},
        ],
    )


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
    """Export endpoint aggregates tool calls from the harness event log."""
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
    """toolSummary is null when no tool activity exists in the event log."""
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
async def test_export_tool_summary_null_when_no_tool_events(
    async_client: httpx.AsyncClient,
) -> None:
    """toolSummary is None when the event log exists but contains no tool events."""
    chat_id = f"test-export-notool-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)
    _write_event_log(chat_id, [])

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["toolSummary"] is None


@pytest.mark.asyncio
async def test_export_tool_summary_handles_null_duration(
    async_client: httpx.AsyncClient,
) -> None:
    """tool_end without duration_ms in the event log is treated as 0."""
    from datetime import datetime, timezone

    chat_id = f"test-export-nulldur-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    base_ts = datetime.now(tz=timezone.utc).timestamp() - 10
    _write_event_log(
        chat_id,
        [
            {"ts": base_ts, "type": "tool_start", "data": {"tool_name": "web_search", "tool_call_id": "call-1", "query": "test"}},
            {"ts": base_ts + 1.0, "type": "tool_end", "data": {"tool_name": "web_search", "tool_call_id": "call-1"}},
        ],
    )

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
    """Tool calls from multiple assistant turns are aggregated correctly."""
    from datetime import datetime, timezone

    chat_id = f"test-export-multi-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    base_ts = datetime.now(tz=timezone.utc).timestamp() - 10
    _write_event_log(
        chat_id,
        [
            {"ts": base_ts, "type": "tool_start", "data": {"tool_name": "web_search", "tool_call_id": "call-1", "query": "a"}},
            {"ts": base_ts + 0.5, "type": "tool_end", "data": {"tool_name": "web_search", "tool_call_id": "call-1", "duration_ms": 500}},
            {"ts": base_ts + 1.0, "type": "tool_start", "data": {"tool_name": "web_search", "tool_call_id": "call-2", "query": "b"}},
            {"ts": base_ts + 1.3, "type": "tool_end", "data": {"tool_name": "web_search", "tool_call_id": "call-2", "duration_ms": 300}},
            {"ts": base_ts + 2.0, "type": "tool_start", "data": {"tool_name": "code_exec", "tool_call_id": "call-3", "cmd": "ls"}},
            {"ts": base_ts + 3.0, "type": "tool_end", "data": {"tool_name": "code_exec", "tool_call_id": "call-3", "duration_ms": 1000}},
        ],
    )

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


@pytest.mark.asyncio
async def test_export_chat_includes_agent_info(
    async_client: httpx.AsyncClient,
) -> None:
    """Export includes agentInfo when chat is linked to an agent."""
    from app.database.models.agent import Agent
    from app.database.models.chat import Chat, Message
    from app.platform_utils import get_session_factory

    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    chat_id = f"test-export-agent-{uuid.uuid4().hex[:8]}"

    from datetime import datetime, timezone

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(Agent(id=agent_id, name="Code Reviewer", description="Reviews code quality", model_selection={"model": "gpt-4o"}))
        db.add(Chat(id=chat_id, agent_id=agent_id, title="Agent Chat", action_mode="fast", source="web"))
        db.add(Message(id=f"msg-{uuid.uuid4().hex[:8]}", chat_id=chat_id, role="user", content="Hello", sent_at=datetime.now(tz=timezone.utc), sent_timezone="UTC"))
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    agent_info = res.json()["data"]["agentInfo"]
    assert agent_info is not None
    assert agent_info["name"] == "Code Reviewer"
    assert agent_info["model"] == "gpt-4o"
    assert agent_info["description"] == "Reviews code quality"


@pytest.mark.asyncio
async def test_export_chat_agent_info_null_without_agent(
    async_client: httpx.AsyncClient,
) -> None:
    """agentInfo is null when chat has no linked agent."""
    chat_id = f"test-export-noagent-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text
    assert res.json()["data"]["agentInfo"] is None


@pytest.mark.asyncio
async def test_export_chat_includes_tool_call_details(
    async_client: httpx.AsyncClient,
) -> None:
    """Export includes toolCallDetails with per-call name, argsSummary, durationMs, success."""
    from datetime import datetime, timezone

    chat_id = f"test-export-details-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    base_ts = datetime.now(tz=timezone.utc).timestamp() - 10
    _write_event_log(
        chat_id,
        [
            {"ts": base_ts, "type": "tool_start", "data": {"tool_name": "read_file", "tool_call_id": "call-1", "path": "/src/utils.ts"}},
            {"ts": base_ts + 0.12, "type": "tool_end", "data": {"tool_name": "read_file", "tool_call_id": "call-1", "duration_ms": 120}},
            {"ts": base_ts + 0.5, "type": "tool_start", "data": {"tool_name": "grep_search", "tool_call_id": "call-2", "pattern": "useEffect", "path": "src/"}},
            {"ts": base_ts + 0.85, "type": "tool_end", "data": {"tool_name": "grep_search", "tool_call_id": "call-2", "duration_ms": 350}},
        ],
    )

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    details = res.json()["data"]["toolCallDetails"]
    assert details is not None
    assert len(details) == 2
    assert details[0]["name"] == "read_file"
    assert details[0]["turnIndex"] == 0
    assert details[0]["durationMs"] == 120
    assert details[0]["success"] is True
    assert "path=/src/utils.ts" in details[0]["argsSummary"]
    assert details[1]["name"] == "grep_search"
    assert details[1]["success"] is True


@pytest.mark.asyncio
async def test_export_tool_call_details_sanitizes_sensitive_args(
    async_client: httpx.AsyncClient,
) -> None:
    """Tool call argsSummary redacts fields containing 'key', 'secret', 'token'."""
    from datetime import datetime, timezone

    chat_id = f"test-export-sanitize-{uuid.uuid4().hex[:8]}"
    await _create_chat_with_messages(chat_id)

    base_ts = datetime.now(tz=timezone.utc).timestamp() - 10
    _write_event_log(
        chat_id,
        [
            {"ts": base_ts, "type": "tool_start", "data": {"tool_name": "http_request", "tool_call_id": "call-1", "api_key": "sk-1234secret", "url": "https://example.com"}},
            {"ts": base_ts + 0.2, "type": "tool_end", "data": {"tool_name": "http_request", "tool_call_id": "call-1", "duration_ms": 200}},
        ],
    )

    res = await async_client.get(f"/api/v1/chats/{chat_id}/export")
    assert res.status_code == 200, res.text

    details = res.json()["data"]["toolCallDetails"]
    assert len(details) == 1
    assert "sk-1234secret" not in details[0]["argsSummary"]
    assert "***" in details[0]["argsSummary"]
    assert "https://example.com" in details[0]["argsSummary"]
    assert details[0]["success"] is True
