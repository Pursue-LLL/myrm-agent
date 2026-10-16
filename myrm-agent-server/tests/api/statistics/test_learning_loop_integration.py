"""Contract and integration tests for the /statistics/learning-loop/status endpoint.

Sources are doubled with signature-enforcing autospecs (a drifted call fails the test) and every
sentinel value is distinct, so a counter wired to the wrong source cannot go unnoticed. Ring 1 reads
real event-log files, including a session that ends on several days. One test runs against the real
database to pin ring 2/3 to the exact counters the skill growth page shows.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import create_autospec, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.types import EventPayload, StructuredEvent
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.database.connection import get_db, get_session
from app.database.models import ApprovalRecord, Base, Chat
from app.platform_utils import get_database_engine, reset_database_engine
from app.services.memory.command_center.command_center_memory_scan import ALL_MEMORY_TYPES
from app.services.memory.manager_deps import get_crud_memory_manager
from app.services.skills.draft_notification import notify_skill_draft_created
from app.services.skills.growth.queries import SkillGrowthDashboardStatsRead, summarize_skill_growth_dashboard_stats
from tests.support.minimal_app import build_minimal_app

STATUS_URL = "/api/v1/statistics/learning-loop/status"
LOOP_MODULE = "app.api.statistics.learning_loop"

MEMORIES_BY_TYPE = {
    MemoryType.PROFILE: 3,
    MemoryType.SEMANTIC: 5,
    MemoryType.EPISODIC: 7,
    MemoryType.PROCEDURAL: 11,
    MemoryType.CONVERSATION: 13,
    MemoryType.CLAIM: 17,
    MemoryType.TASK_DIGEST: 19,
}
SKILL_COUNT = 2
CONVERSATION_COUNT = 9
SECONDS_PER_DAY = 86400
# Sessions that ended inside the default 30-day window, as days before now; "spanning" and "late" end twice.
SESSION_END_DAYS_AGO = {
    "recent": (0.5,),
    "yesterday": (1.5,),
    "spanning": (2.5, 0.5),
    "last-week": (4.5,),
    "late": (5.5, 3.5),
}

CONTRACT_PAYLOAD = {
    "ring1_reflection": {"sessions_in_window": 5},
    "ring2_distillation": {"cases_total": 206, "cases_auto_applied": 11, "total_skills": SKILL_COUNT},
    "ring3_advancement": {"cases_pending_review": 72, "cases_blocked": 4},
    "ring4_consolidation": {"total_memories": sum(MEMORIES_BY_TYPE.values())},
    "ring5_profiling": {"conversations": CONVERSATION_COUNT, "profile_entries": MEMORIES_BY_TYPE[MemoryType.PROFILE]},
}


async def _write_events(log_dir: Path, session_id: str, event_type: str, *days_ago: float) -> None:
    now = time.time()
    events = [
        StructuredEvent(
            sequence=index,
            timestamp=now - days * SECONDS_PER_DAY,
            event_type=event_type,
            session_id=session_id,
            data=EventPayload(),
        )
        for index, days in enumerate(days_ago, start=1)
    ]
    await FileEventLogBackend(log_dir=log_dir, session_id=session_id).append(events)


@pytest.fixture()
def app():
    return build_minimal_app(preset="statistics")


@pytest.fixture()
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture()
def event_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An existing event-log directory registered as the server's canonical one."""
    monkeypatch.setattr(settings.database, "event_log_dir", str(tmp_path))
    return tmp_path


@pytest.fixture()
async def event_log_sessions(event_log_dir: Path) -> Path:
    """Five distinct sessions that ended in the window (seven ``session_end`` events across seven days),
    plus a session that ended long ago and one that never ended; neither may be counted."""
    for session_id, days_ago in SESSION_END_DAYS_AGO.items():
        await _write_events(event_log_dir, session_id, "session_end", *days_ago)
    await _write_events(event_log_dir, "long-ago", "session_end", 90)
    await _write_events(event_log_dir, "still-running", "tool_call", 0.5)
    return event_log_dir


@pytest.fixture()
def memory_manager(app):
    """Signature-enforcing manager double returning a distinct count per memory type."""
    manager = create_autospec(MemoryManager, instance=True)
    manager.count_memories.side_effect = lambda memory_type, **_: MEMORIES_BY_TYPE[memory_type]
    app.dependency_overrides[get_crud_memory_manager] = lambda: manager
    return manager


@pytest.fixture()
def database(app):
    """Session double answering the conversation count query."""
    session = create_autospec(AsyncSession, instance=True)
    session.execute.return_value = SimpleNamespace(scalar_one=lambda: CONVERSATION_COUNT)
    app.dependency_overrides[get_db] = lambda: session
    return session


@pytest.fixture()
def growth_stats() -> Iterator[object]:
    with patch(
        f"{LOOP_MODULE}.summarize_skill_growth_dashboard_stats",
        autospec=True,
        return_value=SkillGrowthDashboardStatsRead(total=206, pending_review=72, auto_applied=11, blocked=4),
    ) as stats:
        yield stats


@pytest.fixture()
def skill_catalog() -> Iterator[object]:
    with patch(
        f"{LOOP_MODULE}.skills_service.list_skills",
        autospec=True,
        return_value=[SimpleNamespace(id=f"skill-{index}") for index in range(SKILL_COUNT)],
    ) as list_skills:
        yield list_skills


async def _fetch_payload(client: AsyncClient, days: int = 30) -> dict[str, dict[str, int] | None]:
    resp = await client.get(STATUS_URL, params={"days": days})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    return body["data"]


@pytest.mark.asyncio
class TestLearningLoopContract:
    async def test_each_ring_reports_the_counters_of_its_own_source(
        self, client, event_log_dir, memory_manager, database, growth_stats, skill_catalog, event_log_sessions
    ):
        payload = await _fetch_payload(client)

        assert payload == CONTRACT_PAYLOAD

    async def test_ring1_counts_a_session_once_and_only_inside_the_requested_window(
        self, client, event_log_sessions, memory_manager, database, growth_stats, skill_catalog
    ):
        wide = await _fetch_payload(client, days=30)
        one_day = await _fetch_payload(client, days=1)

        assert wide["ring1_reflection"] == {"sessions_in_window": len(SESSION_END_DAYS_AGO)}
        assert one_day["ring1_reflection"] == {"sessions_in_window": 2}

    async def test_missing_event_log_dir_means_zero_sessions_not_an_unavailable_ring(
        self, client, tmp_path, monkeypatch, memory_manager, database, growth_stats, skill_catalog
    ):
        monkeypatch.setattr(settings.database, "event_log_dir", str(tmp_path / "absent"))

        payload = await _fetch_payload(client)

        assert payload["ring1_reflection"] == {"sessions_in_window": 0}

    @pytest.mark.parametrize(
        ("broken_source", "unavailable_rings"),
        [
            ("event_log", {"ring1_reflection"}),
            ("growth_stats", {"ring2_distillation", "ring3_advancement"}),
            ("skill_catalog", {"ring2_distillation"}),
            ("memory_manager", {"ring4_consolidation", "ring5_profiling"}),
            ("database", {"ring5_profiling"}),
            ("memory_count", {"ring4_consolidation", "ring5_profiling"}),
        ],
    )
    async def test_an_unreadable_source_only_blanks_the_rings_that_depend_on_it(
        self,
        client,
        app,
        monkeypatch,
        event_log_sessions,
        memory_manager,
        database,
        growth_stats,
        skill_catalog,
        broken_source: str,
        unavailable_rings: set[str],
    ):
        def unreadable_event_log(_backend: FileEventLogBackend) -> list[str]:
            raise RuntimeError("event log unreadable")

        def count_with_unreadable_claims(memory_type: MemoryType, **_: object) -> int:
            if memory_type is MemoryType.CLAIM:
                raise RuntimeError("claims unreadable")
            return MEMORIES_BY_TYPE[memory_type]

        breakers: dict[str, Callable[[], None]] = {
            "event_log": lambda: monkeypatch.setattr(FileEventLogBackend, "get_all_session_ids", unreadable_event_log),
            "growth_stats": lambda: setattr(growth_stats, "side_effect", RuntimeError("approvals unreadable")),
            "skill_catalog": lambda: setattr(skill_catalog, "side_effect", RuntimeError("catalog unreadable")),
            "memory_manager": lambda: app.dependency_overrides.__setitem__(get_crud_memory_manager, lambda: None),
            "database": lambda: setattr(database.execute, "side_effect", RuntimeError("database unreadable")),
            "memory_count": lambda: setattr(memory_manager.count_memories, "side_effect", count_with_unreadable_claims),
        }
        breakers[broken_source]()

        payload = await _fetch_payload(client)

        expected = {ring: (None if ring in unavailable_rings else value) for ring, value in CONTRACT_PAYLOAD.items()}
        assert payload == expected


@pytest.fixture()
async def real_database() -> AsyncIterator[None]:
    await reset_database_engine()
    async with get_database_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_session() as db:
        approvals_before = set((await db.execute(select(ApprovalRecord.id))).scalars())
        chats_before = set((await db.execute(select(Chat.id))).scalars())
    yield
    async with get_session() as db:
        await db.execute(delete(ApprovalRecord).where(ApprovalRecord.id.not_in(approvals_before)))
        await db.execute(delete(Chat).where(Chat.id.not_in(chats_before)))
        await db.commit()
    await reset_database_engine()


@pytest.mark.asyncio
async def test_real_rows_move_ring2_ring3_with_the_skill_growth_page_and_ring5_with_chats(
    client, event_log_dir, memory_manager, skill_catalog, real_database
):
    before = await _fetch_payload(client)

    await notify_skill_draft_created(
        {
            "has_value": True,
            "user_id": f"learning_loop_{uuid4().hex}",
            "type": "skill_draft",
            "skill_name": "learning-loop-draft",
            "skill_description": "Draft that must show up as awaiting review",
            "trigger_condition": "When counting",
            "skill_steps": "1. Count",
        }
    )
    async with get_session() as db:
        db.add(Chat(id=f"learning-loop-{uuid4().hex}"))
        await db.commit()
        real_chats = (await db.execute(select(func.count(Chat.id)))).scalar_one()

    after = await _fetch_payload(client)
    page_stats = await summarize_skill_growth_dashboard_stats()

    assert after["ring2_distillation"]["cases_total"] == before["ring2_distillation"]["cases_total"] + 1
    assert after["ring3_advancement"]["cases_pending_review"] == before["ring3_advancement"]["cases_pending_review"] + 1
    assert after["ring2_distillation"]["cases_total"] == page_stats.total
    assert after["ring2_distillation"]["cases_auto_applied"] == page_stats.auto_applied
    assert after["ring3_advancement"]["cases_pending_review"] == page_stats.pending_review
    assert after["ring3_advancement"]["cases_blocked"] == page_stats.blocked
    assert after["ring5_profiling"]["conversations"] == real_chats == before["ring5_profiling"]["conversations"] + 1


def test_memory_fixture_covers_every_memory_type() -> None:
    assert set(MEMORIES_BY_TYPE) == set(ALL_MEMORY_TYPES)
