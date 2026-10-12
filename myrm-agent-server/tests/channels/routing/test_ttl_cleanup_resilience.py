"""Periodic TTL cleanup of channel routing state: it must log at INFO without raising, and the
janitor must outlive a failing sweep."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.routing.stream_manager import (
    AdaptiveThrottler,
    BlockChunker,
    ChunkConfig,
    IncrementalEditor,
    ProgressEstimator,
    StreamCoordinator,
)

_STREAM_LOGGER = "myrm.channels.stream_manager"
_ROUTER_LOGGER = "app.channels.routing.router"


def _expired_progress_estimator() -> ProgressEstimator:
    estimator = ProgressEstimator(session_ttl_seconds=0.001)
    estimator.start_session("s1", "hello")
    time.sleep(0.01)
    return estimator


def _expired_stream_coordinator() -> StreamCoordinator:
    degradation = MagicMock()
    degradation.get_slowdown_multiplier.return_value = 1.0
    coordinator = StreamCoordinator(
        BlockChunker(ChunkConfig(block_size=10)),
        IncrementalEditor(),
        AdaptiveThrottler(),
        degradation,
        session_ttl_seconds=0.001,
    )
    coordinator.should_send_update("s1", "a" * 60)
    time.sleep(0.01)
    return coordinator


@pytest.mark.parametrize(
    "make_cleaner",
    [_expired_progress_estimator, _expired_stream_coordinator],
    ids=["progress-estimator", "stream-coordinator"],
)
def test_expired_session_cleanup_logs_at_info_without_raising(
    make_cleaner: Callable[[], ProgressEstimator | StreamCoordinator],
    caplog: pytest.LogCaptureFixture,
) -> None:
    cleaner = make_cleaner()

    with caplog.at_level(logging.INFO, logger=_STREAM_LOGGER):
        assert cleaner.cleanup_expired_sessions() == 1

    messages = [record.getMessage() for record in caplog.records if record.name == _STREAM_LOGGER]
    assert any("count=1" in message for message in messages)


def _make_router() -> AgentRouter:
    bus = MagicMock()
    bus.consume_inbound = AsyncMock(side_effect=TimeoutError)
    return AgentRouter(bus=bus, pairing_store=MagicMock(), agent_executor=MagicMock())


class TestJanitorResilience:
    @pytest.mark.asyncio
    async def test_failing_sweep_does_not_end_the_janitor(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr("app.channels.routing.router._JANITOR_INTERVAL", 0.01)
        router = _make_router()
        sweeps = 0

        def fail_on_first_sweep() -> int:
            nonlocal sweeps
            sweeps += 1
            if sweeps == 1:
                raise RuntimeError("sweep exploded")
            return 0

        router._stream_coordinator.cleanup_expired_sessions = fail_on_first_sweep  # type: ignore[method-assign]

        with caplog.at_level(logging.ERROR, logger=_ROUTER_LOGGER):
            router._start_janitor()
            janitor = router._janitor_task
            assert janitor is not None
            try:
                for _ in range(300):
                    if sweeps >= 2 or janitor.done():
                        break
                    await asyncio.sleep(0.01)
            finally:
                await router._stop_janitor()

        assert sweeps >= 2
        assert janitor.done()
        failures = [record for record in caplog.records if record.name == _ROUTER_LOGGER and record.exc_info]
        assert len(failures) == 1
        assert "[JANITOR]" in failures[0].getMessage()
