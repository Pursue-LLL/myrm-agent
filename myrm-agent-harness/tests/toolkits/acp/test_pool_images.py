"""RuntimePool image passthrough: only a backend that declares it takes images gets them."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import (
    BackendCapabilities,
    McpServerConfig,
    RuntimeConfig,
    RuntimeEventType,
    create_event,
)


def _pool_with_backend(supports_images: bool, captured: list[list[str] | None]) -> RuntimePool:
    pool = RuntimePool(max_concurrent=1)
    pool.register("claude", RuntimeConfig(backend_type="cli", command="claude"))
    backend = MagicMock()
    backend.capabilities = BackendCapabilities(supports_images=supports_images)

    async def fake_run_turn(
        prompt: str,
        session_id: str,
        *,
        mcp_servers: list[McpServerConfig] | None = None,
        images: list[str] | None = None,
    ):
        captured.append(images)
        yield create_event(RuntimeEventType.DONE, session_id, stop_reason="end_turn")

    backend.run_turn = fake_run_turn
    pool.get = MagicMock(return_value=backend)
    return pool


@pytest.mark.asyncio
async def test_a_backend_that_takes_images_gets_the_files_of_the_turn() -> None:
    captured: list[list[str] | None] = []
    pool = _pool_with_backend(True, captured)

    async for _ in pool.run_turn("claude", "look", session_id="s1", images=["/img/a.png", "/img/b.png"]):
        pass

    assert captured == [["/img/a.png", "/img/b.png"]]


@pytest.mark.asyncio
async def test_a_backend_that_does_not_take_images_is_told_nothing_and_the_skip_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    captured: list[list[str] | None] = []
    pool = _pool_with_backend(False, captured)

    with caplog.at_level("INFO", logger="myrm_agent_harness.toolkits.acp.runtime.pool"):
        async for _ in pool.run_turn("claude", "look", session_id="s1", images=["/img/a.png"]):
            pass

    assert captured == [None]
    assert any("pool_images_skipped" in r.message and "images=1" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_a_turn_without_images_passes_none_and_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    captured: list[list[str] | None] = []
    pool = _pool_with_backend(True, captured)

    with caplog.at_level("INFO", logger="myrm_agent_harness.toolkits.acp.runtime.pool"):
        async for _ in pool.run_turn("claude", "hello", session_id="s1"):
            pass
        async for _ in pool.run_turn("claude", "hello", session_id="s1", images=[]):
            pass

    assert captured == [None, None]
    assert not any("pool_images_skipped" in r.message for r in caplog.records)
