"""The scheduled checkpoint-history pass prunes the live checkpointer and is harmless when it cannot."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver, empty_checkpoint
from langgraph.checkpoint.memory import MemorySaver
from myrm_agent_harness.runtime.checkpointing import create_checkpointer

from app.platform_utils import _reset_checkpointer_for_testing, set_checkpointer
from app.services.system.checkpoint_history_service import run_checkpoint_history_prune

THREAD_ID = "chat-1"


def _config(checkpoint_id: str | None = None) -> RunnableConfig:
    configurable = {"thread_id": THREAD_ID, "checkpoint_ns": ""}
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


async def _append_checkpoint(saver: BaseCheckpointSaver[str], step: int) -> str:
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": f"state of step {step}"}
    await saver.aput(_config(), checkpoint, {"source": "loop", "step": step, "parents": {}}, {})
    return checkpoint["id"]


async def _stored_checkpoint_count(saver: BaseCheckpointSaver[str]) -> int:
    return len([item async for item in saver.alist(_config())])


@pytest_asyncio.fixture
async def sqlite_checkpointer(tmp_path: Path) -> AsyncIterator[BaseCheckpointSaver[str]]:
    """The checkpointer the server builds at startup, registered as the global one."""
    saver, cleanup = await create_checkpointer(mode="sqlite", sqlite_db_path=str(tmp_path / "checkpoints.db"))
    set_checkpointer(saver)
    yield saver
    _reset_checkpointer_for_testing()
    await cleanup()


async def test_only_the_newest_checkpoint_of_a_chat_survives_a_pass(sqlite_checkpointer: BaseCheckpointSaver[str]) -> None:
    for step in range(4):
        await _append_checkpoint(sqlite_checkpointer, step)
    newest = await _append_checkpoint(sqlite_checkpointer, 4)
    assert await _stored_checkpoint_count(sqlite_checkpointer) == 5

    assert await run_checkpoint_history_prune() is True

    assert await _stored_checkpoint_count(sqlite_checkpointer) == 1
    resumed = await sqlite_checkpointer.aget_tuple(_config())
    assert resumed is not None
    assert resumed.checkpoint["id"] == newest


async def test_a_checkpointer_that_cannot_prune_is_left_alone() -> None:
    saver = MemorySaver()
    set_checkpointer(saver)
    try:
        await _append_checkpoint(saver, 0)
        await _append_checkpoint(saver, 1)

        assert await run_checkpoint_history_prune() is False

        assert await _stored_checkpoint_count(saver) == 2
    finally:
        _reset_checkpointer_for_testing()


async def test_a_pass_before_the_checkpointer_exists_is_reported_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    _reset_checkpointer_for_testing()

    with caplog.at_level(logging.WARNING, logger="app.services.system.checkpoint_history_service"):
        assert await run_checkpoint_history_prune() is False

    assert "Checkpoint history prune failed" in caplog.text


async def test_a_failing_pass_is_logged_and_the_job_survives(
    sqlite_checkpointer: BaseCheckpointSaver[str], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def broken(*_: object, **__: object) -> None:
        raise OSError("disk went away")

    monkeypatch.setattr(sqlite_checkpointer, "aprune", broken)
    await _append_checkpoint(sqlite_checkpointer, 0)
    await _append_checkpoint(sqlite_checkpointer, 1)

    with caplog.at_level(logging.WARNING, logger="app.services.system.checkpoint_history_service"):
        assert await run_checkpoint_history_prune() is False

    assert "Checkpoint history prune failed" in caplog.text
    assert await _stored_checkpoint_count(sqlite_checkpointer) == 2
