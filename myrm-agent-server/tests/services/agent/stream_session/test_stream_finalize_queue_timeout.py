"""Tests for structured AgentQueueTimeout error rendering in stream_finalize."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

import orjson
import pytest

from app.services.agent.gateway import AgentQueueTimeout
from app.services.agent.stream_session import stream_finalize
from app.services.agent.stream_session.stream_session_types import AgentStreamSession


def _make_session(locale: str | None = None) -> AgentStreamSession:
    session = cast(AgentStreamSession, MagicMock(spec=AgentStreamSession))
    session.params = MagicMock(message_id="msg-1", locale=locale)
    session.request = MagicMock(chat_id=None, turn_capability_telemetry=None)
    session.collector = MagicMock()
    return session


async def _collect_payload(
    exc: AgentQueueTimeout, locale: str | None = None
) -> dict[str, object]:
    session = _make_session(locale)
    chunks = [
        chunk
        async for chunk in stream_finalize.yield_stream_exception_chunks(session, exc)
    ]
    assert len(chunks) == 1
    raw = chunks[0]
    assert raw.startswith("data: ")
    return cast(dict[str, object], orjson.loads(raw[len("data: ") :]))


class TestQueueTimeoutStructuredError:
    @pytest.mark.asyncio
    async def test_user_limit_zh(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s) — user concurrency limit reached (3 active)",
            reason="user_limit",
            active_sessions=[
                {"chatId": "chat-a", "agentType": "general", "elapsedSeconds": 12.5},
                {"chatId": "chat-b", "agentType": "general", "elapsedSeconds": 3.2},
            ],
        )
        payload = await _collect_payload(exc, "zh-CN")
        assert payload["type"] == "error"
        assert payload["error_kind"] == "concurrency_limit"
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert diag["error_type"] == "concurrency_limit"
        assert diag["locale"] == "zh"
        assert "并发会话已达上限" in str(diag["user_message"])
        assert "chat-a" in str(diag["user_message"])
        assert isinstance(diag["resolution_steps"], list)
        assert len(diag["resolution_steps"]) == 2

    @pytest.mark.asyncio
    async def test_user_limit_en(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s)",
            reason="user_limit",
            active_sessions=[
                {"chatId": "chat-a", "agentType": "general", "elapsedSeconds": 5.0}
            ],
        )
        payload = await _collect_payload(exc, "en-US")
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert diag["locale"] == "en"
        assert "Concurrency limit reached" in str(diag["user_message"])
        assert "chat-a" in str(diag["user_message"])

    @pytest.mark.asyncio
    async def test_memory_pressure(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s) — Memory pressure (CRITICAL)",
            reason="memory_pressure",
        )
        payload = await _collect_payload(exc, "zh-CN")
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert "内存压力" in str(diag["user_message"])

    @pytest.mark.asyncio
    async def test_global_limit_no_holders(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s) — active=20/20",
            reason="global_limit",
            active_sessions=[],
        )
        payload = await _collect_payload(exc, None)
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert diag["locale"] == "en"
        assert "Server is busy" in str(diag["user_message"])

    @pytest.mark.asyncio
    async def test_holders_truncated_at_three(self) -> None:
        exc = AgentQueueTimeout(
            "Queue timeout (10s)",
            reason="global_limit",
            active_sessions=[
                {"chatId": f"chat-{i}", "agentType": "general", "elapsedSeconds": 1.0}
                for i in range(5)
            ],
        )
        payload = await _collect_payload(exc, "en")
        diag = payload["diagnostic_result"]
        assert isinstance(diag, dict)
        assert "chat-0" in str(diag["user_message"])
        assert "+2 more" in str(diag["user_message"])
