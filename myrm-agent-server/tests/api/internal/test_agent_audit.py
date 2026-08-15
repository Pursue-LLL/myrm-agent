"""Unit tests for CP → sandbox agent audit pull endpoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

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
async def test_agent_audit_returns_events_within_window(
    audit_app: FastAPI, event_log_dir: Path
) -> None:
    """Events inside the time window are returned; older ones are filtered out."""
    mock_event = type(
        "MockEvent",
        (),
        {
            "sequence": 1,
            "timestamp": 1_700_000_000.0,
            "event_type": "tool_start",
            "session_id": "sess-1",
            "data": type(
                "MockPayload", (), {"model_dump": lambda self: {"tool_name": "bash"}}
            )(),
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
async def test_agent_audit_filters_by_session_id(
    audit_app: FastAPI, event_log_dir: Path
) -> None:
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
async def test_agent_audit_merges_and_sorts_desc(
    audit_app: FastAPI, event_log_dir: Path
) -> None:
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
async def test_agent_audit_truncates_to_limit(
    audit_app: FastAPI, event_log_dir: Path
) -> None:
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
async def test_agent_audit_counts_security_deny_decisions(
    audit_app: FastAPI, event_log_dir: Path
) -> None:
    """security_deny_total counts BLOCK/DENY/REDACT/LEAK decisions, not ALLOW."""

    def make_event(
        seq: int, ts: float, event_type: str, payload: dict[str, object]
    ) -> object:
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
