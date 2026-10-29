"""Unit tests for the session analytics events timeline.

[TESTS]
- /session/{session_id}: 事件时间线只含类型与时间戳，不回传事件 payload（工具参数、命令行、输出文本），详情由脱敏后的 trace 端点提供
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.statistics.session_analytics import get_session_analytics

_SESSION_ID = "sess-analytics-timeline-001"
_PASSWORD = "Pr0dDbPassw0rd!"


def _mock_db(session_id: str) -> AsyncMock:
    chat = MagicMock()
    chat.id = session_id
    chat.title = "Timeline"
    chat.action_mode = "auto"
    chat.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    chat.compacted_at = None
    chat.compacted_tokens_saved = 0

    chat_result = MagicMock()
    chat_result.scalar_one_or_none.return_value = chat
    counts_result = MagicMock()
    counts_result.one.return_value = MagicMock(total_messages=0, user_messages=0, assistant_messages=0)
    usage_result = MagicMock()
    usage_result.all.return_value = []

    db = AsyncMock()
    db.execute.side_effect = [chat_result, counts_result, usage_result]
    return db


@pytest.mark.asyncio
async def test_the_events_timeline_carries_no_event_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        {"seq": 1, "sid": _SESSION_ID, "type": "session_start", "ts": 1700000000.0, "data": {}},
        {
            "seq": 2,
            "sid": _SESSION_ID,
            "type": "tool_start",
            "ts": 1700000001.0,
            "data": {"tool_call_id": "c1", "tool_name": "bash", "args": {"command": f"mysql -p{_PASSWORD}"}},
        },
        {
            "seq": 3,
            "sid": _SESSION_ID,
            "type": "tool_end",
            "ts": 1700000002.0,
            "data": {"tool_call_id": "c1", "tool_name": "bash", "result": f"password={_PASSWORD}"},
        },
    ]
    (tmp_path / f"{_SESSION_ID}.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    from app.config.settings import settings

    monkeypatch.setattr(settings.database, "event_log_dir", str(tmp_path))

    response = await get_session_analytics(_SESSION_ID, db=_mock_db(_SESSION_ID))

    assert response.status_code == 200
    timeline = json.loads(response.body.decode("utf-8"))["data"]["events_timeline"]
    assert [entry["type"] for entry in timeline] == ["session_start", "tool_start", "tool_end"]
    assert all(set(entry) == {"type", "timestamp"} for entry in timeline)
    assert _PASSWORD not in response.body.decode("utf-8")
