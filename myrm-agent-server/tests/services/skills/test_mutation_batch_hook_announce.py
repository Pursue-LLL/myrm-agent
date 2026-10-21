"""ServerSkillManageBatchHook announces the batch it committed to the chat stream, and only after the commit."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.meta_tools.skills.manage.batch_runner import SkillBatchSnapshot
from myrm_agent_harness.utils.runtime.progress_sink import set_tool_progress_sink

from app.services.skills.mutation_batch_hook import ServerSkillManageBatchHook
from app.services.skills.mutation_batch_stream import build_batch_committed_event

BATCH_ID = "a1b2c3d4-e5f6-4789-a012-3456789abcde"
SNAPSHOTS = {
    "skill-a": SkillBatchSnapshot(skill_name="skill-a", skill_md="a", resources={}, existed_before_batch=True),
}


class _RecordingSink:
    """Progress sink that logs into a call list shared with the session so the order is observable."""

    def __init__(self, calls: list[str]) -> None:
        self.events: list[dict[str, object]] = []
        self._calls = calls

    async def emit(self, event: dict[str, object]) -> None:
        self._calls.append("emit")
        self.events.append(event)


class _FailingSink:
    async def emit(self, event: dict[str, object]) -> None:
        raise RuntimeError("stream closed")


@pytest.fixture(autouse=True)
def _no_sink_leaks() -> Iterator[None]:
    yield
    set_tool_progress_sink(None)


async def _commit_batch(calls: list[str], resolved_id: str | None = "id-a") -> AsyncMock:
    """Run the hook against a recording session; the session appends 'commit' to ``calls`` when committed."""
    session = AsyncMock()
    session.commit.side_effect = lambda: calls.append("commit")
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    storage = MagicMock()
    storage._get_session = MagicMock(return_value=session)
    service = MagicMock()
    service.insert_mutation_batch_snapshot = AsyncMock()

    with (
        patch("app.services.skill_optimization.bootstrap.get_skill_optimization_storage", return_value=storage),
        patch("app.services.skills.write_orchestrator.resolve_skill_id_by_name", AsyncMock(return_value=resolved_id)),
        patch("app.services.skill_optimization.rollback_service.RollbackService", return_value=service),
    ):
        await ServerSkillManageBatchHook().on_batch_committed(BATCH_ID, SNAPSHOTS)
    return session


async def test_batch_is_announced_after_the_snapshots_are_committed() -> None:
    calls: list[str] = []
    sink = _RecordingSink(calls)
    set_tool_progress_sink(sink)

    await _commit_batch(calls)

    assert calls == ["commit", "emit"]
    assert sink.events == [build_batch_committed_event(BATCH_ID)]


async def test_nothing_is_announced_when_a_snapshot_cannot_be_persisted() -> None:
    calls: list[str] = []
    sink = _RecordingSink(calls)
    set_tool_progress_sink(sink)

    with pytest.raises(RuntimeError, match="unresolved skill name"):
        await _commit_batch(calls, resolved_id=None)

    assert sink.events == []


async def test_a_failing_stream_does_not_fail_the_committed_batch(caplog: pytest.LogCaptureFixture) -> None:
    calls: list[str] = []
    set_tool_progress_sink(_FailingSink())

    with caplog.at_level(logging.WARNING, logger="app.services.skills.mutation_batch_hook"):
        session = await _commit_batch(calls)

    session.commit.assert_awaited_once()
    assert any("Failed to announce committed skill batch" in record.getMessage() for record in caplog.records)


async def test_batch_commits_when_no_stream_is_attached() -> None:
    calls: list[str] = []
    set_tool_progress_sink(None)

    session = await _commit_batch(calls)

    session.commit.assert_awaited_once()
    assert calls == ["commit"]
