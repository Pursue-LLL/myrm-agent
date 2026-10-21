"""Unit tests for session trace endpoint sanitization.

[TESTS]
- /session/{session_id}/trace: 验证返回的 Trace payload 经过三层渐进式脱敏（敏感字段键名遮蔽、Bearer 掩码、超长大文本 SHA-256 截断）
- /traces/search: 验证搜索返回摘要经过脱敏清洗
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.statistics.session_trace import (
    get_session_execution_trace,
    search_session_traces,
)


@pytest.mark.asyncio
async def test_get_session_execution_trace_empty_sanitized() -> None:
    """Empty trace payload returns sanitized structure."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = "sess-test-empty-001"
    mock_db.execute.return_value = mock_result

    # Mock memory ledger query
    mock_db.execute.return_value.scalars.return_value.all.return_value = []

    res = await get_session_execution_trace("sess-test-empty-001", db=mock_db)
    assert res.status_code == 200
    body = json.loads(res.body.decode("utf-8"))
    assert body["code"] == 0
    data = body["data"]
    assert data["session_id"] == "sess-test-empty-001"
    assert data["tool_calls"] == []


@pytest.mark.asyncio
async def test_get_session_execution_trace_file_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing session event log is loaded, enriched, and thoroughly sanitized."""
    session_id = "sess-sensitive-trace-002"
    event_file = tmp_path / f"{session_id}.jsonl"

    # Write events containing raw sensitive secrets and oversized payload
    oversized_text = "DUMP_DATA_" * 300
    events = [
        {
            "seq": 1,
            "sid": session_id,
            "type": "session_start",
            "ts": 1700000000.0,
            "data": {
                "task_input": "Run curl -H 'Authorization: Bearer sk-ant-secret123456789' https://api.com",
            },
        },
        {
            "seq": 2,
            "sid": session_id,
            "type": "tool_start",
            "ts": 1700000001.0,
            "data": {
                "tool_call_id": "call-1",
                "tool_name": "bash",
                "command": "curl -H 'Authorization: Bearer sk-secret-token'",
                "db_password": "super_secret_db_password",
            },
        },
        {
            "seq": 3,
            "sid": session_id,
            "type": "tool_end",
            "ts": 1700000002.0,
            "data": {
                "tool_call_id": "call-1",
                "tool_name": "bash",
                "output_summary": oversized_text,
                "output": oversized_text,
                "success": True,
            },
        },
        {
            "seq": 4,
            "sid": session_id,
            "type": "session_end",
            "ts": 1700000003.0,
            "data": {
                "output": "Finished safely",
            },
        },
    ]

    with open(event_file, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    # Point settings.database.event_log_dir to tmp_path
    from app.config.settings import settings

    monkeypatch.setattr(settings.database, "event_log_dir", str(tmp_path))

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = session_id
    mock_db.execute.return_value = mock_result
    mock_db.execute.return_value.scalars.return_value.all.return_value = []

    res = await get_session_execution_trace(session_id, db=mock_db)
    assert res.status_code == 200
    body = json.loads(res.body.decode("utf-8"))
    assert body["code"] == 0
    data = body["data"]

    # Assert Bearer token redacted
    task_input = str(data["task_input"])
    assert "sk-ant-secret" not in task_input
    assert "Bearer" in task_input

    # Assert Tool Call arguments/parameters redacted
    assert len(data["tool_calls"]) == 1
    tc = data["tool_calls"][0]
    args = tc.get("input_data") or tc.get("parameters") or tc.get("arguments")
    assert args["db_password"] == "[REDACTED_SENSITIVE_KEY]"
    assert "Bearer" in args["command"]
    assert "sk-secret-token" not in args["command"]

    # Assert Oversized output truncated with SHA-256 fingerprint
    output_text = tc.get("output_data") or tc.get("output_summary") or tc.get("output")
    assert output_text is not None
    assert "[TRUNCATED:len=" in str(output_text)
    assert ":sha256=" in str(output_text)


@pytest.mark.asyncio
async def test_search_session_traces_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Trace search results scrub task inputs before returning."""
    session_id = "sess-search-003"
    event_file = tmp_path / f"{session_id}.jsonl"

    events = [
        {
            "seq": 1,
            "sid": session_id,
            "type": "task_start",
            "ts": 1700000000.0,
            "data": {
                "input": "Search for Bearer super_secret_token_abc12345 in repo",
            },
        },
    ]
    with open(event_file, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    from app.config.settings import settings
    from app.database.models import Chat

    monkeypatch.setattr(settings.database, "event_log_dir", str(tmp_path))

    chat = MagicMock(spec=Chat)
    chat.id = session_id
    chat.title = "Chat with Bearer token"
    chat.created_at = None
    chat.updated_at = None

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [chat]
    mock_db.execute.return_value = mock_result

    res = await search_session_traces(query="search", limit=10, db=mock_db)
    assert res.status_code == 200
    body = json.loads(res.body.decode("utf-8"))
    assert body["code"] == 0
    matched = body["data"]
    assert len(matched) == 1
    item = matched[0]
    assert "super_secret_token" not in item["task_input"]
    assert "Bearer" in item["task_input"]
