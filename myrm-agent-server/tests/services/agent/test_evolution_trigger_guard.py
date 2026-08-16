"""Guard tests for trigger_skill_evolution dedup + capture threshold.

Verifies that consecutive turns of the same chat cannot start concurrent
evolution tasks (asyncio task names do not enforce uniqueness) and that plain
chat turns below the capture threshold are skipped.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.agent.evolution import engine as evolution_engine


@pytest.mark.asyncio
async def test_duplicate_trigger_while_pending_is_skipped() -> None:
    """A second trigger for the same chat while a task is in flight is a no-op."""

    started: asyncio.Event = asyncio.Event()
    release: asyncio.Event = asyncio.Event()

    async def _blocking_run(*_args: object, **_kwargs: object) -> None:
        started.set()
        await release.wait()

    original_run = evolution_engine._run_evolution_task
    evolution_engine._run_evolution_task = _blocking_run  # type: ignore[assignment]
    evolution_engine._RUNNING_EVOLUTION_TASKS.clear()
    try:
        evolution_engine.trigger_skill_evolution("chat-dedup-1", object(), tool_steps_count=5)  # type: ignore[arg-type]
        await asyncio.wait_for(started.wait(), timeout=2)

        task = evolution_engine._RUNNING_EVOLUTION_TASKS.get("chat-dedup-1")
        assert task is not None

        evolution_engine.trigger_skill_evolution("chat-dedup-1", object(), tool_steps_count=5)  # type: ignore[arg-type]
        # The in-flight task is not replaced.
        assert evolution_engine._RUNNING_EVOLUTION_TASKS["chat-dedup-1"] is task
    finally:
        release.set()
        pending = evolution_engine._RUNNING_EVOLUTION_TASKS.get("chat-dedup-1")
        if pending is not None:
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, Exception):
                pass
        evolution_engine._run_evolution_task = original_run
        evolution_engine._RUNNING_EVOLUTION_TASKS.clear()


@pytest.mark.asyncio
async def test_shallow_turn_below_threshold_is_skipped() -> None:
    """Plain chat turns under the tool-step threshold never schedule a task."""

    evolution_engine._RUNNING_EVOLUTION_TASKS.clear()

    async def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    original_run = evolution_engine._run_evolution_task
    evolution_engine._run_evolution_task = _noop  # type: ignore[assignment]
    try:
        evolution_engine.trigger_skill_evolution("chat-shallow-1", object(), tool_steps_count=1)  # type: ignore[arg-type]
        assert "chat-shallow-1" not in evolution_engine._RUNNING_EVOLUTION_TASKS
    finally:
        evolution_engine._run_evolution_task = original_run
        evolution_engine._RUNNING_EVOLUTION_TASKS.clear()


@pytest.mark.asyncio
async def test_dw_conversation_text_bypasses_threshold() -> None:
    """Workflow-mode (conversation_text provided) triggers regardless of steps."""

    evolution_engine._RUNNING_EVOLUTION_TASKS.clear()
    started: asyncio.Event = asyncio.Event()
    release: asyncio.Event = asyncio.Event()

    async def _blocking_run(*_args: object, **_kwargs: object) -> None:
        started.set()
        await release.wait()

    original_run = evolution_engine._run_evolution_task
    evolution_engine._run_evolution_task = _blocking_run  # type: ignore[assignment]
    try:
        evolution_engine.trigger_skill_evolution(  # type: ignore[arg-type]
            "chat-dw-1",
            object(),
            tool_steps_count=0,
            conversation_text="collected workflow content",
        )
        await asyncio.wait_for(started.wait(), timeout=2)
        assert "chat-dw-1" in evolution_engine._RUNNING_EVOLUTION_TASKS
    finally:
        release.set()
        pending = evolution_engine._RUNNING_EVOLUTION_TASKS.get("chat-dw-1")
        if pending is not None:
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, Exception):
                pass
        evolution_engine._run_evolution_task = original_run
        evolution_engine._RUNNING_EVOLUTION_TASKS.clear()
