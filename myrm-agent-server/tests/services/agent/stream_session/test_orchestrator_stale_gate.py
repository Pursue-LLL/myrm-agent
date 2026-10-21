"""Web orchestrator pre-reply stale compact gate wiring tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.chat.compact_service import CompactResult
from app.services.chat.stale_compact_gate import run_pre_reply_stale_compact_gate


@pytest.mark.asyncio
async def test_run_pre_reply_stale_compact_gate_reads_engine_params() -> None:
    gate_result = CompactResult(compacted=True, tokens_saved=900, message_count=12)
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "app.services.chat.stale_compact_gate.resolve_idle_compact_after_seconds",
            AsyncMock(return_value=1800),
        ) as mock_resolve,
        patch("app.database.connection.get_session", return_value=mock_session),
        patch(
            "app.services.chat.stale_compact_gate.maybe_compact_stale_chat_before_turn",
            AsyncMock(return_value=gate_result),
        ),
    ):
        result = await run_pre_reply_stale_compact_gate(
            "chat-web-1",
            agent_id="default",
            request_engine_params={"idle_compact_after_seconds": 1800},
        )

    assert result.compacted is True
    mock_resolve.assert_awaited_once_with("default", {"idle_compact_after_seconds": 1800})
