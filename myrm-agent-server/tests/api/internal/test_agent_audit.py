"""Unit tests for CP → sandbox agent audit pull endpoint."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.internal import agent_audit as agent_audit_module
from app.api.internal.agent_audit import router as agent_audit_router


@pytest.fixture
def audit_app() -> FastAPI:
    app = FastAPI()
    app.include_router(agent_audit_router)
    return app


@pytest.fixture
def event_log_dir(tmp_path: Path) -> Path:
    log_dir = tmp_path / "event_logs"
    log_dir.mkdir()
    return log_dir


@pytest.mark.asyncio
async def test_agent_audit_empty_when_log_dir_missing(audit_app: FastAPI) -> None:
    """Missing event-log dir returns an empty result, not an error."""
    with patch(
        "app.api.internal.agent_audit.settings",
    ) as mock_settings:
        mock_settings.database.event_log_dir = "/nonexistent/event_logs"
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/agent-audit/events")

    assert resp.status_code == 200
    data = resp.json()
    assert data["events"] == []
    assert data["total"] == 0
    assert data["tool_call_total"] == 0
    assert data["security_event_total"] == 0
    assert data["security_deny_total"] == 0


@pytest.mark.asyncio
async def test_agent_audit_returns_events_within_window(audit_app: FastAPI, event_log_dir: Path) -> None:
    """Events inside the time window are returned; older ones are filtered out."""
    mock_event = type(
        "MockEvent",
        (),
        {
            "sequence": 1,
            "timestamp": 1_700_000_000.0,
            "event_type": "tool_start",
            "session_id": "sess-1",
            "data": type("MockPayload", (), {"model_dump": lambda self: {"tool_name": "bash"}})(),
        },
    )
    mock_backend = AsyncMock()
    mock_backend.get_all_session_ids.return_value = ["sess-1"]
    mock_backend.get_events.return_value = [mock_event]

    with (
        patch(
            "app.api.internal.agent_audit.settings",
        ) as mock_settings,
        patch(
            "app.api.internal.agent_audit.FileEventLogBackend",
            return_value=mock_backend,
        ),
    ):
        mock_settings.database.event_log_dir = str(event_log_dir)
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/agent-audit/events")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["tool_call_total"] == 1
    assert data["security_event_total"] == 0
    event = data["events"][0]
    assert event["seq"] == 1
    assert event["type"] == "tool_start"
    assert event["sid"] == "sess-1"
    assert event["data"] == {"tool_name": "bash"}
    mock_backend.get_events.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_audit_filters_by_session_id(audit_app: FastAPI, event_log_dir: Path) -> None:
    """A single-session query passes the session id through to the backend."""
    mock_backend = AsyncMock()
    mock_backend.get_events.return_value = []

    with (
        patch(
            "app.api.internal.agent_audit.settings",
        ) as mock_settings,
        patch(
            "app.api.internal.agent_audit.FileEventLogBackend",
            return_value=mock_backend,
        ),
    ):
        mock_settings.database.event_log_dir = str(event_log_dir)
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/admin/agent-audit/events?session_id=sess-9",
            )

    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    args = mock_backend.get_events.await_args.args
    assert args[0] == "sess-9"
    event_filter = args[1]
    assert event_filter.start_time is not None
    assert event_filter.limit is None


@pytest.mark.asyncio
async def test_agent_audit_rejects_invalid_hours(audit_app: FastAPI) -> None:
    """Hours outside the allowed window return 400."""
    with patch(
        "app.api.internal.agent_audit.settings",
    ) as mock_settings:
        mock_settings.database.event_log_dir = "/nonexistent"
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/agent-audit/events?hours=0")

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_agent_audit_merges_and_sorts_desc(audit_app: FastAPI, event_log_dir: Path) -> None:
    """Events from multiple sessions are merged and sorted newest-first."""
    mock_backend = AsyncMock()
    mock_backend.get_all_session_ids.return_value = ["sess-1", "sess-2"]
    mock_backend.get_events.side_effect = [
        [
            type(
                "E",
                (),
                {
                    "sequence": 1,
                    "timestamp": 100.0,
                    "event_type": "tool_start",
                    "session_id": "sess-1",
                    "data": type("P", (), {"model_dump": lambda self: {}})(),
                },
            )()
        ],
        [
            type(
                "E",
                (),
                {
                    "sequence": 1,
                    "timestamp": 200.0,
                    "event_type": "tool_start",
                    "session_id": "sess-2",
                    "data": type("P", (), {"model_dump": lambda self: {}})(),
                },
            )()
        ],
    ]

    with (
        patch(
            "app.api.internal.agent_audit.settings",
        ) as mock_settings,
        patch(
            "app.api.internal.agent_audit.FileEventLogBackend",
            return_value=mock_backend,
        ),
    ):
        mock_settings.database.event_log_dir = str(event_log_dir)
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/agent-audit/events")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["tool_call_total"] == 2
    assert [e["ts"] for e in data["events"]] == [200.0, 100.0]
    assert mock_backend.get_events.await_count == 2


@pytest.mark.asyncio
async def test_agent_audit_truncates_to_limit(audit_app: FastAPI, event_log_dir: Path) -> None:
    """Returned events are capped while total reflects the full match count."""
    mock_backend = AsyncMock()
    mock_backend.get_all_session_ids.return_value = ["sess-1"]
    mock_backend.get_events.return_value = [
        type(
            "E",
            (),
            {
                "sequence": i,
                "timestamp": float(i),
                "event_type": "tool_start",
                "session_id": "sess-1",
                "data": type("P", (), {"model_dump": lambda self: {}})(),
            },
        )()
        for i in range(1, 6)
    ]

    with (
        patch(
            "app.api.internal.agent_audit.settings",
        ) as mock_settings,
        patch(
            "app.api.internal.agent_audit.FileEventLogBackend",
            return_value=mock_backend,
        ),
    ):
        mock_settings.database.event_log_dir = str(event_log_dir)
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/agent-audit/events?limit=2")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert data["tool_call_total"] == 5
    assert len(data["events"]) == 2


@pytest.mark.asyncio
async def test_agent_audit_counts_security_deny_decisions(audit_app: FastAPI, event_log_dir: Path) -> None:
    """security_deny_total counts BLOCK/DENY/REDACT/LEAK decisions, not ALLOW."""

    def make_event(seq: int, ts: float, event_type: str, payload: dict[str, object]) -> object:
        return type(
            "E",
            (),
            {
                "sequence": seq,
                "timestamp": ts,
                "event_type": event_type,
                "session_id": "sess-1",
                "data": type("P", (), {"model_dump": lambda self, p=payload: p})(),
            },
        )()

    mock_backend = AsyncMock()
    mock_backend.get_all_session_ids.return_value = ["sess-1"]
    mock_backend.get_events.return_value = [
        make_event(
            1,
            1_700_000_000.0,
            "security_audit",
            {
                "decisions": [
                    {"tool": "bash", "decision": "ALLOW", "reason": "benign"},
                    {"tool": "bash", "decision": "DENY", "reason": "blocked"},
                    {"tool": "read_file", "decision": "PII_REDACTED", "reason": "pii"},
                    {"tool": "bash", "decision": "CRON_DENY", "reason": "cron policy"},
                ],
                "count": 4,
            },
        ),
        make_event(2, 1_700_000_100.0, "security_audit", {"decisions": [], "count": 0}),
        make_event(3, 1_700_000_200.0, "tool_start", {"tool_name": "bash"}),
    ]

    with (
        patch(
            "app.api.internal.agent_audit.settings",
        ) as mock_settings,
        patch(
            "app.api.internal.agent_audit.FileEventLogBackend",
            return_value=mock_backend,
        ),
    ):
        mock_settings.database.event_log_dir = str(event_log_dir)
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/agent-audit/events")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["tool_call_total"] == 1
    # 2 security_audit 事件（会话级），但 deny 决策 3 个（DENY/PII_REDACTED/CRON_DENY）
    assert data["security_event_total"] == 2
    assert data["security_deny_total"] == 3


@pytest.mark.asyncio
async def test_agent_audit_real_jsonl_full_pipeline(audit_app: FastAPI, event_log_dir: Path) -> None:
    """真实 event-log 全链路：真实 JSONL 写入 → 真实 harness FileEventLogBackend → deny 计数。

    关键路径禁 mock：仅 patch 配置指向临时日志目录；事件经 harness 真实序列化落盘。
    """
    now = time.time()
    lines = [
        json.dumps(
            {
                "seq": 1,
                "ts": round(now, 3),
                "type": "security_audit",
                "sid": "sess-a",
                "data": {
                    "decisions": [
                        {"decision": "ALLOW", "reason": "benign"},
                        {"decision": "DENY", "reason": "blocked"},
                        {"decision": "PII_REDACTED", "reason": "pii"},
                    ]
                },
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "seq": 2,
                "ts": round(now - 1, 3),
                "type": "tool_start",
                "sid": "sess-a",
                "data": {"tool_name": "bash"},
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "seq": 1,
                "ts": round(now - 2, 3),
                "type": "security_audit",
                "sid": "sess-b",
                "data": {"decisions": [{"decision": "ALLOW"}]},
            },
            ensure_ascii=False,
        ),
    ]
    (event_log_dir / "sess-a.jsonl").write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")
    # 第二个会话单独一个文件，验证 get_all_session_ids 扫描到两个会话。
    (event_log_dir / "sess-b.jsonl").write_text(lines[2] + "\n", encoding="utf-8")

    with patch.object(agent_audit_module.settings.database, "event_log_dir", str(event_log_dir)):
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/agent-audit/events?hours=24&limit=50")

    assert resp.status_code == 200
    data = resp.json()
    # 3 条真实事件（跨 2 会话），按 ts 倒序
    assert data["total"] == 3
    assert [e["ts"] for e in data["events"]] == sorted([e["ts"] for e in data["events"]], reverse=True)
    assert data["tool_call_total"] == 1
    # 2 条 security_audit 会话事件，其中 deny 决策 2 个（DENY/PII_REDACTED）
    assert data["security_event_total"] == 2
    assert data["security_deny_total"] == 2
    # 视图字段完整（sess-a 的 DENY 决策数据原样透出）
    first = data["events"][0]
    assert first["sid"] == "sess-a"
    assert first["type"] == "security_audit"
    assert first["data"]["decisions"][1]["decision"] == "DENY"


@pytest.mark.asyncio
async def test_agent_audit_real_jsonl_hours_window_filters_old_events(audit_app: FastAPI, event_log_dir: Path) -> None:
    """真实 JSONL：不超过 hours 时间窗的事件被过滤，计数基于窗口内数据。"""
    now = time.time()
    # 两天前的事件（超过 24h 窗口）
    stale = json.dumps(
        {
            "seq": 1,
            "ts": round(now - 48 * 3600, 3),
            "type": "tool_start",
            "sid": "sess-old",
            "data": {"tool_name": "bash"},
        },
        ensure_ascii=False,
    )
    (event_log_dir / "sess-old.jsonl").write_text(stale + "\n", encoding="utf-8")

    with patch.object(agent_audit_module.settings.database, "event_log_dir", str(event_log_dir)):
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/agent-audit/events?hours=24")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["tool_call_total"] == 0
    assert data["events"] == []


@pytest.mark.asyncio
async def test_agent_audit_rejects_invalid_cp_token(audit_app: FastAPI) -> None:
    """Wrong telemetry token returns 403."""
    with (
        patch.dict("os.environ", {"CONTROL_PLANE_TELEMETRY_TOKEN": "secret123"}),
        patch(
            "app.api.internal.agent_audit.settings",
        ) as mock_settings,
    ):
        mock_settings.database.event_log_dir = "/nonexistent"
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/admin/agent-audit/events",
                headers={"X-Telemetry-Token": "wrong-token"},
            )

    assert resp.status_code == 403
