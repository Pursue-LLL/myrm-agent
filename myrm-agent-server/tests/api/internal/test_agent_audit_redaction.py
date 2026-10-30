"""The agent audit pull re-applies the redaction to what the log stores before it leaves the sandbox."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

_LEGACY_SECRET = "hunter2xyz-audit"
_CALL_ID = "call_00_3nrnFlx48weKv0yTotV43729_vtx8763"


async def _append_unredacted(log_dir: Path, session_id: str, data: dict[str, object]) -> None:
    """Write an event the way a log written before redaction, or by a writer that skipped it, holds it."""
    from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
    from myrm_agent_harness.agent.event_log.types import EventPayload, StructuredEvent

    backend = FileEventLogBackend(log_dir=log_dir, session_id=session_id)
    event = StructuredEvent(
        sequence=1,
        timestamp=time.time(),
        event_type="tool_start",
        session_id=session_id,
        data=EventPayload(**data),
    )
    await backend.append([event])
    await backend.close()


@pytest.mark.asyncio
async def test_agent_audit_never_hands_a_stored_credential_to_the_control_plane(audit_app: FastAPI, event_log_dir: Path) -> None:
    """The log is the record; the pull re-applies the redaction, so a credential an old line holds stays here."""
    await _append_unredacted(
        event_log_dir,
        "sess-legacy",
        {
            "tool_name": "bash",
            "tool_call_id": _CALL_ID,
            "args": {"command": "deploy", "env": {"DB_PASSWORD": _LEGACY_SECRET}},
        },
    )

    with patch("app.api.internal.agent_audit.settings") as mock_settings:
        mock_settings.database.event_log_dir = str(event_log_dir)
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/admin/agent-audit/events")

    assert resp.status_code == 200
    body = resp.json()
    assert _LEGACY_SECRET not in resp.text
    event = body["events"][0]
    assert event["data"]["tool_name"] == "bash"
    assert event["data"]["tool_call_id"] == _CALL_ID
    assert event["data"]["args"]["command"] == "deploy"
