"""Integration: a skill saved through skill_manage can be found in the catalog and undone by batch id.

Only the database engine (in-memory SQLite) and the skills root (tmp dir) are substituted. The tool, the
scanning wrapper, the batch hook, the progress sink, the harness stream handlers, the stream collector, the
catalog and the rollback service are the production code. The batch id is read off the Task Steps entry the
collector builds from the stream, the same place the frontend reads it, so the test fails when the writer's
storage root drifts away from the root the catalog scans, when the stream never links the batch to its step,
or when undo cannot remove a skill that the batch created.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from myrm_agent_harness.agent.streaming.event_handlers import process_updates_chunk
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.utils.runtime.progress_sink import create_queue_sink, set_tool_progress_sink
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.ai_agents.general_agent.tool_setup import ToolSetupMixin
from app.core.skills import models as skill_models
from app.core.skills.creation import service as creation_service_module
from app.core.skills.creation.service import SkillCreationService
from app.core.skills.models import DEFAULT_LOCAL_SKILL_PATHS
from app.database.models import Base
from app.database.models.skill_optimization.batch_snapshot import BatchSnapshot
from app.services.agent.execution_cache import ExecutionMode
from app.services.agent.runtime_context import build_agent_runtime_context
from app.services.agent.streaming_support.stream_collector import StreamContentCollector
from app.services.skills.mutation_batch_service import MutationBatchRollbackError, rollback_skill_mutation_batch
from app.services.skills.write_orchestrator import resolve_skill_id_by_name

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

SKILL_NAME = "lifecycle-demo"
SKILL_MD = f'---\nname: {SKILL_NAME}\ndescription: "Lifecycle demo"\n---\n# Lifecycle demo\n1. Do the thing.\n'
MESSAGE_ID = "msg-lifecycle"
CALL_ID = "call-skill-manage-1"
DELETE_CALL_ID = "call-skill-manage-2"
SECOND_CALL_ID = "call-skill-manage-3"
THIRD_CALL_ID = "call-skill-manage-4"


class _Host(ToolSetupMixin):
    """Smallest host exposing the flags ToolSetupMixin reads."""

    enable_skill_manage = True
    force_skill_manage = False


@pytest.fixture
def skills_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One tmp root serves as the writer's storage root and as the catalog's primary scan root."""
    root = tmp_path / "skills"
    root.mkdir()

    async def _skip_user_config(self: SkillCreationService, skill_dir: Path) -> None:
        return None

    monkeypatch.setattr(SkillCreationService, "_auto_enable_local", _skip_user_config)
    monkeypatch.setattr(SkillCreationService, "_auto_disable_local", _skip_user_config)
    monkeypatch.setattr(skill_models, "DEFAULT_LOCAL_SKILL_PATHS", [str(root)])
    monkeypatch.setattr(creation_service_module.skill_creation_service, "base_path", root)
    return root


@pytest.fixture
async def session_factory(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(
        "app.services.skill_optimization.bootstrap.get_skill_optimization_storage",
        lambda: SQLAlchemyStorage(session_factory=factory),
    )
    yield factory
    await engine.dispose()


@pytest.fixture
def skill_manage_tool(skills_root: Path, session_factory: async_sessionmaker[AsyncSession]) -> BaseTool:
    tools: list[object] = []
    _Host()._setup_skill_manage_tool(tools, creation_service_module.skill_creation_service, object(), None)
    return cast("BaseTool", tools[0])


async def _turn_config() -> RunnableConfig:
    with patch(
        "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
        new_callable=AsyncMock,
        return_value=[],
    ):
        context = await build_agent_runtime_context(execution_mode=ExecutionMode.POOLED)
    return {"configurable": {"context": context}}


async def _feed(collector: StreamContentCollector, events: AsyncGenerator[dict[str, object]]) -> None:
    async for event in events:
        collector.feed_event(event)


async def _run_turn(tool: BaseTool, operations: list[dict[str, object]], call_id: str) -> tuple[str, dict[str, object]]:
    """Run one skill_manage turn through the event path of a live turn; return the tool output and the call's step.

    The model node's update opens the step, the tool runs (its hook pushes events through the progress sink),
    the tool node's update closes it, and the collector sees every event in that order.
    """
    queue: asyncio.Queue[dict[str, object] | object] = asyncio.Queue()
    set_tool_progress_sink(create_queue_sink(queue, MESSAGE_ID))
    collector = StreamContentCollector()
    stats = AgentRunStatistics()
    call = {"name": "skill_manage_tool", "args": {"operations": operations}, "id": call_id}
    try:
        await _feed(
            collector,
            process_updates_chunk({"model": {"messages": [AIMessage(content="", tool_calls=[call])]}}, stats, MESSAGE_ID),
        )
        output = str(await tool.ainvoke({"operations": operations}, config=await _turn_config()))
        reply = ToolMessage(content=output, name="skill_manage_tool", tool_call_id=call_id)
        await _feed(collector, process_updates_chunk({"tools": {"messages": [reply]}}, stats, MESSAGE_ID))
        while not queue.empty():
            collector.feed_event(cast("dict[str, object]", queue.get_nowait()))
    finally:
        set_tool_progress_sink(None)

    steps = cast("list[dict[str, object]]", collector.get_snapshot()["progress_steps"])
    call_steps = [step for step in steps if step.get("tool_call_id") == call_id]
    assert len(call_steps) == 1, steps
    return output, call_steps[0]


def _batch_id_of(step: dict[str, object]) -> str:
    batch_id = step.get("skill_mutation_batch_id")
    assert isinstance(batch_id, str), "the stream never linked the committed batch to its Task Steps entry"
    return batch_id


async def _save_skill(tool: BaseTool) -> str:
    """Save the skill in a live-shaped turn and return the batch id its Task Steps entry carries."""
    output, step = await _run_turn(tool, [{"action": "save", "name": SKILL_NAME, "content": SKILL_MD}], CALL_ID)
    assert "created successfully" in output, output
    return _batch_id_of(step)


def test_catalog_primary_root_is_the_writers_storage_root() -> None:
    """Whatever MYRM_DATA_DIR points at, a skill the agent writes must land in a root the catalog scans."""
    catalog_root = Path(DEFAULT_LOCAL_SKILL_PATHS[0]).expanduser().resolve()

    assert catalog_root == SkillCreationService().base_path.resolve()


async def test_saved_skill_resolves_by_name_and_persists_one_batch_snapshot(
    skill_manage_tool: BaseTool, skills_root: Path, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    batch_id = await _save_skill(skill_manage_tool)

    assert (skills_root / SKILL_NAME / "SKILL.md").is_file()
    assert await resolve_skill_id_by_name(SKILL_NAME) is not None
    async with session_factory() as session:
        rows = (await session.execute(select(BatchSnapshot).where(BatchSnapshot.batch_id == batch_id))).scalars().all()
    assert len(rows) == 1


async def test_undo_removes_the_skill_the_batch_created(
    skill_manage_tool: BaseTool, skills_root: Path, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    batch_id = await _save_skill(skill_manage_tool)

    async with session_factory() as session:
        restored = await rollback_skill_mutation_batch(session, batch_id)

    assert restored == 1
    assert not (skills_root / SKILL_NAME).exists()
    assert await resolve_skill_id_by_name(SKILL_NAME) is None


async def test_deleting_a_skill_is_final_and_leaves_no_undo_record(
    skill_manage_tool: BaseTool, skills_root: Path, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _save_skill(skill_manage_tool)

    output, step = await _run_turn(skill_manage_tool, [{"action": "delete", "name": SKILL_NAME}], DELETE_CALL_ID)

    assert "deleted successfully" in output, output
    # A delete has no snapshot to undo, so its output must not read like a committed batch.
    assert "Batch applied successfully" not in output
    assert not (skills_root / SKILL_NAME).exists()
    assert "skill_mutation_batch_id" not in step, step
    async with session_factory() as session:
        rows = (await session.execute(select(BatchSnapshot))).scalars().all()
    assert len(rows) == 1, "only the save left a snapshot"


async def test_undo_of_a_second_batch_keeps_what_the_first_batch_created(
    skill_manage_tool: BaseTool, skills_root: Path, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _save_skill(skill_manage_tool)
    stored = (skills_root / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8")
    operations: list[dict[str, object]] = [
        {"action": "write_file", "name": SKILL_NAME, "file_path": "references/notes.md", "content": "notes"}
    ]

    output, step = await _run_turn(skill_manage_tool, operations, SECOND_CALL_ID)

    assert "written to skill" in output, output
    async with session_factory() as session:
        await rollback_skill_mutation_batch(session, _batch_id_of(step))
    assert (skills_root / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8") == stored
    assert not (skills_root / SKILL_NAME / "references" / "notes.md").exists()


async def test_undo_of_a_file_removal_puts_the_file_back(
    skill_manage_tool: BaseTool, skills_root: Path, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _save_skill(skill_manage_tool)
    notes = skills_root / SKILL_NAME / "references" / "notes.md"
    written: list[dict[str, object]] = [
        {"action": "write_file", "name": SKILL_NAME, "file_path": "references/notes.md", "content": "notes"}
    ]
    await _run_turn(skill_manage_tool, written, SECOND_CALL_ID)
    removal: list[dict[str, object]] = [{"action": "remove_file", "name": SKILL_NAME, "file_path": "references/notes.md"}]

    output, step = await _run_turn(skill_manage_tool, removal, THIRD_CALL_ID)

    assert "removed from skill" in output, output
    assert not notes.exists()
    async with session_factory() as session:
        await rollback_skill_mutation_batch(session, _batch_id_of(step))
    assert notes.read_text(encoding="utf-8") == "notes"


async def test_undo_of_a_full_rewrite_restores_the_previous_content(
    skill_manage_tool: BaseTool, skills_root: Path, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _save_skill(skill_manage_tool)
    stored = (skills_root / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8")
    rewritten = SKILL_MD.replace("Do the thing.", "Do it differently.")

    output, step = await _run_turn(
        skill_manage_tool, [{"action": "save", "name": SKILL_NAME, "content": rewritten}], SECOND_CALL_ID
    )

    assert "updated successfully" in output, output
    assert (skills_root / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8") == rewritten
    async with session_factory() as session:
        await rollback_skill_mutation_batch(session, _batch_id_of(step))
    assert (skills_root / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8") == stored


async def test_a_patch_edits_a_skill_the_turn_backend_cannot_see_and_undo_puts_the_text_back(
    skill_manage_tool: BaseTool, skills_root: Path, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """The turn's backend (``object()`` here) lists nothing; the patch reads the writer's storage like the snapshot does."""
    await _save_skill(skill_manage_tool)
    skill_md = skills_root / SKILL_NAME / "SKILL.md"
    stored = skill_md.read_text(encoding="utf-8")
    patch: list[dict[str, object]] = [
        {"action": "patch", "name": SKILL_NAME, "old_content": "Do the thing.", "new_content": "Do it differently."}
    ]

    output, step = await _run_turn(skill_manage_tool, patch, SECOND_CALL_ID)

    assert "patched successfully" in output, output
    assert "Do it differently." in skill_md.read_text(encoding="utf-8")
    async with session_factory() as session:
        await rollback_skill_mutation_batch(session, _batch_id_of(step))
    assert skill_md.read_text(encoding="utf-8") == stored


async def test_undo_of_a_rewrite_is_refused_once_the_skill_was_deleted(
    skill_manage_tool: BaseTool, skills_root: Path, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A deleted skill stays deleted: the rewrite's Undo is still on screen, and answering "restored" for it would lie."""
    await _save_skill(skill_manage_tool)
    rewritten = SKILL_MD.replace("Do the thing.", "Do it differently.")
    _, step = await _run_turn(skill_manage_tool, [{"action": "save", "name": SKILL_NAME, "content": rewritten}], SECOND_CALL_ID)
    await _run_turn(skill_manage_tool, [{"action": "delete", "name": SKILL_NAME}], DELETE_CALL_ID)

    async with session_factory() as session:
        with pytest.raises(MutationBatchRollbackError):
            await rollback_skill_mutation_batch(session, _batch_id_of(step))

    assert not (skills_root / SKILL_NAME).exists(), "the undo brought the deleted skill back"
    assert await resolve_skill_id_by_name(SKILL_NAME) is None
