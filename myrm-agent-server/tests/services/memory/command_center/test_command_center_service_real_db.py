"""Command-center projections against a real SQLite database.

Seeds shared contexts, bindings, proposals, ledger events and chat messages, then drives the
aggregation service and the projection modules through the same SQL the production snapshot runs.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryType
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models.base import Base
from app.database.models.chat import Chat, Message
from app.database.models.memory import (
    MemoryHealthSnapshotModel,
    MemoryOperationEventModel,
    SharedContextBindingModel,
    SharedContextModel,
    SharedContextWriteProposalModel,
)
from app.services.memory.command_center.command_center import MemoryCommandCenterService
from app.services.memory.command_center.command_center_health import build_health
from app.services.memory.command_center.command_center_influence import load_influence
from app.services.memory.command_center.command_center_recall_boundary import BUDGET_CHARS_TOTAL, build_recall_boundary
from app.services.memory.command_center.command_center_timeline import build_timeline
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

_NOW = datetime.now(UTC).replace(microsecond=0)
_TABLES = [
    SharedContextModel.__table__,
    SharedContextBindingModel.__table__,
    SharedContextWriteProposalModel.__table__,
    MemoryOperationEventModel.__table__,
    MemoryHealthSnapshotModel.__table__,
    Chat.__table__,
    Message.__table__,
]


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///file:cc_{uuid.uuid4().hex}?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=_TABLES))
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def full_db() -> AsyncIterator[AsyncSession]:
    """Every ORM table: ``build_snapshot`` also reads import, restore and diagnostic ledgers."""
    import app.database.models  # noqa: F401  (registers all tables on Base.metadata)

    engine = create_async_engine(f"sqlite+aiosqlite:///file:ccfull_{uuid.uuid4().hex}?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


def _manager(**overrides: object) -> MagicMock:
    manager = MagicMock()
    manager.namespaces = ["global", "agent:a1", "team:x"]
    manager.memory_policy = None
    manager.has_graph = False
    manager.has_vector = True
    manager.has_relational = True
    manager.vector_is_persistent = True
    manager.count_memories = AsyncMock(return_value=2)
    manager.count_pending = AsyncMock(return_value=0)
    manager.list_pending = AsyncMock(return_value=[])
    manager.list_memories = AsyncMock(return_value=[])
    manager.compute_health_score = AsyncMock(
        return_value=SimpleNamespace(to_dict=lambda: {"total": 90, "dimensions": {}, "suggestions": [], "sample_size": 1})
    )
    for key, value in overrides.items():
        setattr(manager, key, value)
    return manager


async def _seed_shared_contexts(session: AsyncSession) -> None:
    """ctx-a/ctx-b belong to project p1, ctx-c to project p2; ctx-a carries two pending proposals."""
    for index, (context_id, name) in enumerate((("ctx-a", "Alpha"), ("ctx-b", "Beta"), ("ctx-c", "Gamma"))):
        session.add(
            SharedContextModel(
                id=context_id,
                namespace=f"shared:{context_id}",
                name=name,
                description=f"{name} context",
                created_at=_NOW,
                updated_at=_NOW - timedelta(minutes=index),
            )
        )
    await session.flush()
    for binding_id, context_id, project in (
        ("b1", "ctx-a", "p1"),
        ("b2", "ctx-b", "p1"),
        ("b3", "ctx-c", "p2"),
        ("b4", "ctx-a", "p2"),
    ):
        session.add(SharedContextBindingModel(id=binding_id, context_id=context_id, target_type="project", target_id=project))
    for proposal_id, context_id, status, age in (
        ("pr1", "ctx-a", "pending", 3),
        ("pr2", "ctx-a", "pending", 1),
        ("pr3", "ctx-c", "pending", 2),
        ("pr4", "ctx-a", "approved", 0),
    ):
        session.add(
            SharedContextWriteProposalModel(
                id=proposal_id,
                context_id=context_id,
                memory_type="semantic",
                content=f"proposal   {proposal_id}\nwith   spacing",
                status=status,
                created_at=_NOW - timedelta(minutes=age),
            )
        )
    await session.commit()


class TestSpaces:
    @pytest.mark.asyncio
    async def test_global_view_lists_namespaces_and_every_context(self, db: AsyncSession) -> None:
        await _seed_shared_contexts(db)
        spaces = await MemoryCommandCenterService(db, _manager())._build_spaces()

        by_namespace = {space.namespace: space for space in spaces}
        assert by_namespace["global"].kind == "global"
        assert by_namespace["agent:a1"].label == "agent / a1"
        assert by_namespace["team:x"].kind == "unknown"
        assert by_namespace["shared:ctx-a"].binding_count == 2
        assert by_namespace["shared:ctx-a"].context_id == "ctx-a"
        assert {"shared:ctx-a", "shared:ctx-b", "shared:ctx-c"} <= set(by_namespace)

    @pytest.mark.asyncio
    async def test_project_view_only_shows_bound_contexts(self, db: AsyncSession) -> None:
        await _seed_shared_contexts(db)
        spaces = await MemoryCommandCenterService(db, _manager(), project_id="p1")._build_spaces()
        assert [space.namespace for space in spaces] == ["shared:ctx-a", "shared:ctx-b"]

    @pytest.mark.asyncio
    async def test_project_without_bindings_sees_nothing(self, db: AsyncSession) -> None:
        await _seed_shared_contexts(db)
        assert await MemoryCommandCenterService(db, _manager(), project_id="ghost")._build_spaces() == []


class TestGovernance:
    @pytest.mark.asyncio
    async def test_global_view_merges_pending_queue_and_pending_proposals_newest_first(self, db: AsyncSession) -> None:
        await _seed_shared_contexts(db)
        service = MemoryCommandCenterService(db, _manager())
        with patch(
            "app.services.memory.command_center.command_center.build_pending_governance",
            new=AsyncMock(return_value=[]),
        ):
            items = await service._build_governance()
        assert [item.id for item in items] == ["pr2", "pr3", "pr1"]
        assert items[0].description == "proposal pr2 with spacing"
        assert items[0].available_actions == ["approve", "reject", "edit"]

    @pytest.mark.asyncio
    async def test_project_view_filters_proposals_and_skips_the_pending_queue(self, db: AsyncSession) -> None:
        await _seed_shared_contexts(db)
        service = MemoryCommandCenterService(db, _manager(), project_id="p2")
        pending_queue = AsyncMock(return_value=[])
        with patch("app.services.memory.command_center.command_center.build_pending_governance", new=pending_queue):
            items = await service._build_governance()
        assert {item.id for item in items} == {"pr1", "pr2", "pr3"}
        pending_queue.assert_not_awaited()

        empty = MemoryCommandCenterService(db, _manager(), project_id="ghost")
        with patch("app.services.memory.command_center.command_center.build_pending_governance", new=pending_queue):
            assert await empty._build_governance() == []


class TestTimeline:
    @pytest.mark.asyncio
    async def test_empty_ledger_falls_back_to_proposals_contexts_and_health_marker(self, db: AsyncSession) -> None:
        await _seed_shared_contexts(db)
        service = MemoryCommandCenterService(db, _manager())
        with patch(
            "app.services.memory.command_center.command_center_timeline.build_pending_timeline",
            new=AsyncMock(return_value=[]),
        ):
            events = await build_timeline(
                db=db, ledger=service._ledger, memory_manager=service._memory_manager, project_context_ids=None
            )
        sources = {event.source for event in events}
        assert {"shared_context_write_proposal", "shared_context", "memory_manager"} <= sources
        assert all(event.occurred_at.tzinfo is not None for event in events)
        assert events == sorted(events, key=lambda event: event.occurred_at, reverse=True)

    @pytest.mark.asyncio
    async def test_fallback_for_a_project_is_scoped_and_has_no_health_marker(self, db: AsyncSession) -> None:
        await _seed_shared_contexts(db)
        service = MemoryCommandCenterService(db, _manager())
        events = await build_timeline(
            db=db, ledger=service._ledger, memory_manager=service._memory_manager, project_context_ids={"ctx-c"}
        )
        assert {event.namespace for event in events} == {"shared:ctx-c"}
        assert all(event.source != "memory_manager" for event in events)

    @pytest.mark.asyncio
    async def test_ledger_events_win_and_are_namespace_filtered_for_projects(self, db: AsyncSession) -> None:
        ledger = MemoryOperationLedgerService(db)
        await ledger.record_event(kind=MemoryOperationKind.WRITE, summary="in project", namespace="shared:ctx-a")
        await ledger.record_event(kind=MemoryOperationKind.WRITE, summary="elsewhere", namespace="global")
        await db.commit()
        manager = _manager()

        everything = await build_timeline(db=db, ledger=ledger, memory_manager=manager, project_context_ids=None)
        scoped = await build_timeline(db=db, ledger=ledger, memory_manager=manager, project_context_ids={"ctx-a"})
        nothing = await build_timeline(db=db, ledger=ledger, memory_manager=manager, project_context_ids=set())

        assert {event.description for event in everything} == {"in project", "elsewhere"}
        assert [event.description for event in scoped] == ["in project"]
        assert nothing == []


class TestInfluence:
    @pytest.mark.asyncio
    async def test_only_messages_with_cited_refs_become_items(self, db: AsyncSession) -> None:
        db.add(Chat(id="chat-1", action_mode="fast", source="web"))
        await db.flush()
        cited = {
            "citedMemoryRefs": [
                {"id": "mem-1", "memory_type": "semantic", "content": "likes tea", "score": 0.8, "namespaces": ["global"]},
                {"id": 7, "memory_type": "semantic"},
            ],
            "usage": {"prompt_tokens": 100, "cached_tokens": 40},
            "tokenEconomics": {"prompt_tokens": 20},
        }
        for message_id, extra, age in (("m-cited", cited, 0), ("m-plain", {"usage": {}}, 1)):
            db.add(
                Message(
                    id=message_id,
                    chat_id="chat-1",
                    role="assistant",
                    content="answer   text",
                    sent_at=_NOW,
                    sent_timezone="UTC",
                    created_at=_NOW - timedelta(minutes=age),
                    extra_data=extra,
                )
            )
        await db.commit()

        items = await load_influence(db)

        assert [item.message_id for item in items] == ["m-cited"]
        assert items[0].prompt_tokens == 120
        assert items[0].cached_tokens == 40
        assert items[0].answer_preview == "answer text"
        [ref] = items[0].influence_refs
        assert (ref.memory_id, ref.score, ref.primary_namespace) == ("mem-1", 0.8, "global")


class TestHealth:
    @pytest.mark.asyncio
    async def test_refresh_computes_persists_and_then_serves_the_cache(self, db: AsyncSession) -> None:
        ledger = MemoryOperationLedgerService(db)
        report = SimpleNamespace(
            to_dict=lambda: {"total": 82.0, "dimensions": {"freshness": 0.9}, "suggestions": ["prune"], "sample_size": 12}
        )
        manager = _manager(compute_health_score=AsyncMock(return_value=report))

        refreshed = await build_health(db=db, ledger=ledger, memory_manager=manager, force_refresh=True)
        assert (refreshed.status, refreshed.total, refreshed.cache_status) == ("healthy", 82, "refreshed")
        assert refreshed.dimensions == {"freshness": 0.9}
        assert refreshed.sample_size == 12

        cached = await build_health(db=db, ledger=ledger, memory_manager=manager)
        assert (cached.status, cached.total, cached.cache_status) == ("healthy", 82, "fresh")
        assert manager.compute_health_score.await_count == 1
        kinds = [event.kind for event in await ledger.list_events()]
        assert kinds == [MemoryOperationKind.HEALTH_CHECK.value]

    @pytest.mark.asyncio
    async def test_failed_computation_degrades_to_an_unknown_score(self, db: AsyncSession) -> None:
        manager = _manager(compute_health_score=AsyncMock(side_effect=RuntimeError("vector store down")))
        health = await build_health(db=db, ledger=MemoryOperationLedgerService(db), memory_manager=manager, force_refresh=True)
        assert (health.status, health.total, health.cache_status) == ("unknown", None, "refreshed")


class _Memory:
    def __init__(self, memory_id: str, content: str) -> None:
        self.id = memory_id
        self.content = content
        self.primary_namespace = "global"


class TestRecallBoundary:
    @staticmethod
    def _manager_with(chars: int) -> MagicMock:
        def _list(memory_type: MemoryType, **_: object) -> list[_Memory]:
            if memory_type == MemoryType.PROFILE:
                return [_Memory("profile-1", "p" * 100)]
            if memory_type == MemoryType.SEMANTIC:
                return [_Memory("sem-1", "s" * chars)]
            if memory_type == MemoryType.PROCEDURAL:
                return [_Memory("proc-1", "r" * 50)]
            if memory_type == MemoryType.TASK_DIGEST:
                return [_Memory("task-1", "t" * 10)]
            return []

        manager = _manager()
        manager.list_memories = AsyncMock(side_effect=_list)
        return manager

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("chars", "risk"),
        [(100, "safe"), (4400, "approaching_limit"), (BUDGET_CHARS_TOTAL, "overflow")],
    )
    async def test_partitions_and_budget_risk(self, db: AsyncSession, chars: int, risk: str) -> None:
        manager = self._manager_with(chars)
        with patch(
            "app.services.memory.command_center.command_center_recall_boundary.build_candidate_records",
            new=AsyncMock(return_value=[]),
        ):
            data = await build_recall_boundary(db, manager, agent_id="a1", task_id="t1")

        partitions = data.partitions
        assert (partitions.identity_count, partitions.operating_instructions_count) == (1, 1)
        assert (partitions.working_memory_count, partitions.retrievable_evidence_count) == (1, 1)
        assert partitions.retrievable_evidence_chars == chars
        assert data.budget_chars_used == 100 + chars + 50 + 10
        assert data.budget_chars_total == BUDGET_CHARS_TOTAL
        assert data.budget_overflow_risk == risk
        assert data.total_approved == 4
        assert data.write_policy == "inherit"
        levels = {scope.level: scope for scope in data.read_scopes}
        assert levels["agent"].label == "Agent Dedicated (a1)"
        assert levels["task"].namespace_pattern == "task:t1"
        assert all(scope.is_active for scope in data.read_scopes)

    @pytest.mark.asyncio
    async def test_a_failing_type_is_skipped_without_aborting_the_snapshot(self, db: AsyncSession) -> None:
        manager = _manager()

        async def _list(memory_type: MemoryType, **_: object) -> list[_Memory]:
            if memory_type == MemoryType.SEMANTIC:
                raise RuntimeError("store offline")
            return [_Memory("profile-1", "hello")] if memory_type == MemoryType.PROFILE else []

        manager.list_memories = AsyncMock(side_effect=_list)
        with patch(
            "app.services.memory.command_center.command_center_recall_boundary.build_candidate_records",
            new=AsyncMock(return_value=[]),
        ):
            data = await build_recall_boundary(db, manager)
        assert data.total_approved == 1
        assert data.approved_records[0].partition == "identity"


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_assembles_every_section_from_a_real_database(self, full_db: AsyncSession) -> None:
        await _seed_shared_contexts(full_db)
        ledger = MemoryOperationLedgerService(full_db)
        await ledger.record_event(
            kind=MemoryOperationKind.RECALL,
            summary="trace step",
            source="memory_retrieval_trace",
            namespace="shared:ctx-a",
            metadata={"trace_id": "t-1", "step_index": 1, "query_preview": "tea"},
        )
        await full_db.commit()

        snapshot = await MemoryCommandCenterService(full_db, _manager()).build_snapshot()

        assert snapshot.overview.total_memories == 14
        assert snapshot.overview.pending_shared_proposals == 3
        assert snapshot.overview.active_shared_contexts == 3
        assert (snapshot.health.status, snapshot.health.total) == ("healthy", 90)
        assert snapshot.overview.health_status == "healthy"
        assert {space.namespace for space in snapshot.spaces} >= {"global", "shared:ctx-a"}
        assert [item.id for item in snapshot.governance] == ["pr2", "pr3", "pr1"]
        assert [run.trace_id for run in snapshot.trace_runs] == ["t-1"]
        assert snapshot.trace_runs[0].query_preview == "tea"
        assert snapshot.live_stream == snapshot.timeline[:12]
        assert len(snapshot.replay_events) == len(snapshot.timeline)
        assert [step.phase for step in snapshot.waterfall][:2] == ["observe", "scan"]
        assert snapshot.runtime.vector_persistence == "persistent"
        assert snapshot.plane_summary.event_count == len(snapshot.timeline)

    @pytest.mark.asyncio
    async def test_project_snapshot_is_scoped_to_the_bound_contexts(self, full_db: AsyncSession) -> None:
        await _seed_shared_contexts(full_db)

        snapshot = await MemoryCommandCenterService(full_db, _manager(), project_id="p1").build_snapshot()

        assert {space.namespace for space in snapshot.spaces} == {"shared:ctx-a", "shared:ctx-b"}
        assert {item.id for item in snapshot.governance} == {"pr1", "pr2"}
        assert all(event.namespace in {"shared:ctx-a", "shared:ctx-b"} for event in snapshot.timeline)
        assert all(event.source != "memory_manager" for event in snapshot.timeline)
