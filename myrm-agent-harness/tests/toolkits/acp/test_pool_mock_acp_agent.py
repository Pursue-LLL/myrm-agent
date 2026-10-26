"""RuntimePool driving a real ACP agent subprocess (the mock echo agent) end to end."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import RuntimeConfig, RuntimeEventType

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="process liveness is probed with POSIX signals")

_MOCK_AGENT = Path(__file__).with_name("_mock_acp_agent.py")


async def _wait_until_gone(pid: int, *, timeout: float = 5.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.mark.asyncio
async def test_pool_round_trips_through_an_acp_process_and_close_all_stops_it(tmp_path: Path) -> None:
    pool = RuntimePool(max_concurrent=1, enable_health_monitor=True)
    pool.register(
        "mock",
        RuntimeConfig(
            backend_type="acp",
            command=sys.executable,
            args=[str(_MOCK_AGENT)],
            cwd=str(tmp_path),
            timeout_seconds=30,
        ),
    )
    await pool.start_monitoring()
    text: list[str] = []
    try:
        async for event in pool.run_turn("mock", "ping", session_id="chat-1"):
            if event.type == RuntimeEventType.TEXT_DELTA:
                text.append(str(event.data.get("content")))
        backend = pool.get("mock")
        process = getattr(backend, "_process", None)
        assert process is not None
        pid = process.pid
        assert "mock" in pool.get_health_metrics()
    finally:
        await pool.close_all()

    assert "[echo] ping" in "".join(text)
    assert await _wait_until_gone(pid)
