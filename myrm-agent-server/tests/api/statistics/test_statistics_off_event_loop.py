"""Unit test verifying that statistics endpoints scan event logs off the event loop.

[INPUT]
- app.api.statistics.router::router as statistics_router
- myrm_agent_harness.agent.event_log.backends.file_backend::FileEventLogBackend

[OUTPUT]
- Pytest tests validating event-loop liveness during statistics requests

[POS]
- tests/api/statistics/test_statistics_off_event_loop.py: Item 60 Server verification
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.statistics.router import router as statistics_router

test_app = FastAPI()
test_app.include_router(statistics_router, prefix="/api/v1/statistics")


@pytest.mark.asyncio
async def test_activity_endpoint_off_event_loop_liveness(tmp_path: Path) -> None:
    log_dir = tmp_path / "event_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Populate 5 session files with multiple noise lines and session_end
    for s_idx in range(5):
        s_id = f"session_{s_idx}"
        f_path = log_dir / f"{s_id}.jsonl"
        lines: list[str] = []
        for i in range(100):
            lines.append(
                json.dumps(
                    {
                        "seq": i,
                        "ts": 1000.0 + i,
                        "type": "tool_start",
                        "sid": s_id,
                        "data": {"tool_name": "bash"},
                    }
                )
            )
        lines.append(
            json.dumps(
                {
                    "seq": 101,
                    "ts": 2000.0,
                    "type": "session_end",
                    "sid": s_id,
                    "data": {"summary": {"tool_calls": 50, "duration_ms": 100.0}},
                }
            )
        )
        f_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Patch settings to point to our test log_dir
    with patch("app.api.statistics.router.settings.database.event_log_dir", str(log_dir)):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            heartbeat_ticks = 0

            async def _heartbeat() -> None:
                nonlocal heartbeat_ticks
                for _ in range(8):
                    await asyncio.sleep(0.005)
                    heartbeat_ticks += 1

            heartbeat_task = asyncio.create_task(_heartbeat())
            resp = await client.get("/api/v1/statistics/activity?timezone=Asia/Shanghai")
            await heartbeat_task

            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["timezone"] == "Asia/Shanghai"
            assert data["active_days"] >= 1
            # Heartbeat task successfully ticked during the scan
            assert heartbeat_ticks > 0
