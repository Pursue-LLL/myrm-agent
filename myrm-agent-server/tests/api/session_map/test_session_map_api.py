"""
[INPUT]
- FastAPI app mounting the Session Map router over a real in-memory SQLite database
- Project, Chat and ApprovalRecord rows seeded straight into that database
- A stubbed AgentGateway reporting which chats have a turn in flight

[OUTPUT]
- Tests pinning project clustering, runtime-state inference, cockpit totals, state filtering, search, and the
  absence of placeholder data (an empty store is empty, a database failure is an error)

[POS]
API tests for the Project-Centric Session Map and Agent State Cockpit.
Strict typing: Zero `Any`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.context_management.strategies.compression.compression_anti_thrash_guard import (
    ANTI_THRASHING_STREAK_LIMIT,
)
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.session_map.models import (
    FleetCockpitSummary,
    ProjectClusterModel,
    SessionSearchResponse,
)
from app.api.session_map.routes import _infer_session_state
from app.api.session_map.routes import router as session_map_router
from app.database.connection import get_db
from app.database.models import ApprovalRecord, Base, Chat
from app.database.models.project import Project

_PREFIX = "/api/v1/session-map"
_NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
_RUNNING = frozenset({"chat-working"})
_CLUSTERS = TypeAdapter(list[ProjectClusterModel])


@pytest.fixture()
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    # StaticPool shares one connection: a plain ``:memory:`` SQLite would give every connection its own empty database.
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
def client(db_engine: AsyncEngine) -> Iterator[TestClient]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _real_session() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(session_map_router, prefix=_PREFIX)
    app.dependency_overrides[get_db] = _real_session
    gateway = SimpleNamespace(active_session_ids=lambda: _RUNNING)
    with patch("app.api.session_map.routes.get_agent_gateway", return_value=gateway), TestClient(app) as test_client:
        yield test_client


def _chat(
    chat_id: str,
    title: str,
    *,
    project_id: str | None = None,
    tags: list[str] | None = None,
    tokens: int = 0,
    streak: int = 0,
    age_minutes: int = 0,
) -> Chat:
    stamp = _NOW - timedelta(minutes=age_minutes)
    return Chat(
        id=chat_id,
        title=title,
        project_id=project_id,
        tags=tags or [],
        total_tokens=tokens,
        compression_ineffective_streak=streak,
        created_at=stamp,
        updated_at=stamp,
    )


def _approval(
    approval_id: str,
    chat_id: str | None,
    status: str,
    *,
    action_type: str = "shell_command",
    thread_id: str | None = None,
) -> ApprovalRecord:
    return ApprovalRecord(
        id=approval_id, agent_id="agent-1", chat_id=chat_id, thread_id=thread_id, action_type=action_type, status=status
    )


def _seed(db_engine: AsyncEngine, *rows: Project | Chat | ApprovalRecord) -> None:
    async def _insert() -> None:
        async with AsyncSession(db_engine) as session:
            session.add_all(rows)
            await session.commit()

    asyncio.run(_insert())


def _seed_fleet(db_engine: AsyncEngine) -> None:
    """Two projects and one unassigned chat: a running, a ready, an approval-blocked and a failing session."""
    _seed(
        db_engine,
        Project(id="proj-a", name="Alpha", workspace_path="/work/alpha", sort_order=0),
        Project(id="proj-b", name="Beta", workspace_path=None, sort_order=1),
        _chat("chat-working", "Refactor auth", project_id="proj-a", tags=["security"], tokens=1000, age_minutes=1),
        _chat("chat-ready", "Write release notes", project_id="proj-a", tokens=500, age_minutes=5),
        _chat("chat-waiting", "Deploy staging", tokens=200, age_minutes=2),
        _chat("chat-error", "Flaky tests", project_id="proj-b", tokens=300, streak=4, age_minutes=10),
        _approval("ap-pending", "chat-waiting", "PENDING"),
        _approval("ap-resolved", "chat-ready", "APPROVED"),
        _approval("ap-unbound", None, "PENDING"),
    )


def _projects(client: TestClient, **params: str) -> dict[str, ProjectClusterModel]:
    response = client.get(f"{_PREFIX}/projects", params=params)
    assert response.status_code == 200
    return {cluster.name: cluster for cluster in _CLUSTERS.validate_python(response.json())}


def _states(clusters: dict[str, ProjectClusterModel]) -> dict[str, str]:
    return {s.id: s.state for cluster in clusters.values() for s in cluster.sessions}


def test_an_empty_store_has_no_projects_sessions_or_totals(client: TestClient) -> None:
    assert client.get(f"{_PREFIX}/projects").json() == []

    cockpit = FleetCockpitSummary.model_validate(client.get(f"{_PREFIX}/cockpit").json())
    assert cockpit == FleetCockpitSummary()


def test_projects_cluster_their_chats_and_unassigned_chats_get_the_global_bucket(
    client: TestClient, db_engine: AsyncEngine
) -> None:
    _seed_fleet(db_engine)

    clusters = _projects(client)

    assert list(clusters) == ["Alpha", "Beta", "Global Workspace"]
    assert [s.id for s in clusters["Alpha"].sessions] == ["chat-working", "chat-ready"]
    assert [s.id for s in clusters["Beta"].sessions] == ["chat-error"]
    assert [s.id for s in clusters["Global Workspace"].sessions] == ["chat-waiting"]
    assert clusters["Alpha"].total_tokens == 1500
    assert clusters["Alpha"].active_agent_count == 2
    assert clusters["Beta"].active_agent_count == 0


def test_a_cluster_reports_only_the_workspace_path_the_project_has(client: TestClient, db_engine: AsyncEngine) -> None:
    _seed_fleet(db_engine)

    clusters = _projects(client)
    raw_clusters: list[dict[str, object]] = client.get(f"{_PREFIX}/projects").json()

    assert clusters["Alpha"].workspace_path == "/work/alpha"
    assert clusters["Beta"].workspace_path is None
    assert clusters["Global Workspace"].workspace_path is None
    assert all("git_repo_url" not in raw for raw in raw_clusters)


def test_session_states_follow_the_gateway_pending_approvals_and_compaction_failures(
    client: TestClient, db_engine: AsyncEngine
) -> None:
    _seed_fleet(db_engine)

    assert _states(_projects(client)) == {
        "chat-working": "working",
        "chat-ready": "ready",
        "chat-waiting": "waiting_input",
        "chat-error": "error",
    }


def test_a_background_growth_draft_does_not_hold_its_chat_but_an_inline_one_does(
    client: TestClient, db_engine: AsyncEngine
) -> None:
    """Background drafts are reviewed in the skills inbox (no thread to resume); an inline draft suspends its agent."""
    _seed(
        db_engine,
        _chat("chat-background", "Background proposal"),
        _chat("chat-inline", "Inline proposal"),
        _approval("ap-background", "chat-background", "PENDING", action_type="skill_draft"),
        _approval("ap-inline", "chat-inline", "PENDING", action_type="skill_draft", thread_id="thread-1"),
    )

    assert _states(_projects(client)) == {"chat-background": "ready", "chat-inline": "waiting_input"}


def test_the_state_filter_keeps_only_the_matching_sessions(client: TestClient, db_engine: AsyncEngine) -> None:
    _seed_fleet(db_engine)

    assert _states(_projects(client, state_filter="waiting_input")) == {"chat-waiting": "waiting_input"}


def test_the_cockpit_totals_describe_the_sessions_the_map_shows(client: TestClient, db_engine: AsyncEngine) -> None:
    _seed_fleet(db_engine)

    cockpit = FleetCockpitSummary.model_validate(client.get(f"{_PREFIX}/cockpit").json())

    assert cockpit.total_projects == 3
    assert cockpit.total_sessions == 4
    assert cockpit.total_agents == 4
    assert cockpit.working_agents == 1
    assert cockpit.ready_agents == 1
    assert cockpit.waiting_input_agents == 1
    assert cockpit.error_agents == 1
    assert cockpit.total_tokens_consumed == 2000
    assert [s.id for s in cockpit.top_active_sessions] == ["chat-working", "chat-waiting", "chat-ready", "chat-error"]


def test_search_ranks_title_matches_and_reports_the_matched_field(client: TestClient, db_engine: AsyncEngine) -> None:
    _seed_fleet(db_engine)

    by_title = SessionSearchResponse.model_validate(client.post(f"{_PREFIX}/search", json={"query": "release"}).json())
    by_tag = SessionSearchResponse.model_validate(client.post(f"{_PREFIX}/search", json={"query": "security"}).json())

    assert [h.session.id for h in by_title.hits] == ["chat-ready"]
    assert by_title.hits[0].project_name == "Alpha"
    assert by_title.hits[0].matched_snippet == "Title matched: Write release notes"
    assert [h.session.id for h in by_tag.hits] == ["chat-working"]
    assert by_tag.hits[0].matched_snippet == "Tag: #security"


def test_search_can_be_scoped_to_a_project_or_a_state(client: TestClient, db_engine: AsyncEngine) -> None:
    _seed_fleet(db_engine)

    in_alpha = SessionSearchResponse.model_validate(
        client.post(f"{_PREFIX}/search", json={"query": "e", "project_id": "proj-a"}).json()
    )
    waiting = SessionSearchResponse.model_validate(
        client.post(f"{_PREFIX}/search", json={"query": "e", "state": "waiting_input"}).json()
    )
    nothing = SessionSearchResponse.model_validate(
        client.post(f"{_PREFIX}/search", json={"query": "nonexistent_query_xyz_999999"}).json()
    )

    assert {h.session.id for h in in_alpha.hits} == {"chat-working", "chat-ready"}
    assert [h.session.id for h in waiting.hits] == ["chat-waiting"]
    assert (nothing.total_hits, nothing.hits) == (0, [])


def test_a_database_failure_is_an_error_not_placeholder_data() -> None:
    class _BrokenSession:
        async def execute(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("database unavailable")

    async def _broken_session() -> AsyncGenerator[_BrokenSession, None]:
        yield _BrokenSession()

    app = FastAPI()
    app.include_router(session_map_router, prefix=_PREFIX)
    app.dependency_overrides[get_db] = _broken_session
    with TestClient(app, raise_server_exceptions=False) as broken:
        assert broken.get(f"{_PREFIX}/projects").status_code == 500
        assert broken.get(f"{_PREFIX}/cockpit").status_code == 500
        assert broken.post(f"{_PREFIX}/search", json={"query": "anything"}).status_code == 500


def _bare_chat(chat_id: str, *, streak: int = 0, compacted_before_id: str | None = None) -> Chat:
    return Chat(
        id=chat_id,
        total_calls=5,
        last_read_at=None,
        compression_ineffective_streak=streak,
        compacted_before_id=compacted_before_id,
    )


def test_a_chat_is_working_exactly_while_the_gateway_has_a_turn_in_flight() -> None:
    """Past usage never makes a chat look busy; only a live turn does."""
    chat = _bare_chat("chat-state-1")

    assert _infer_session_state(chat, frozenset({"chat-state-1"}), frozenset()) == "working"
    assert _infer_session_state(chat, frozenset(), frozenset()) == "ready"


def test_a_compacted_chat_without_a_live_turn_is_idle() -> None:
    chat = _bare_chat("chat-state-2", compacted_before_id="msg-9")

    assert _infer_session_state(chat, frozenset(), frozenset()) == "idle"


def test_a_pending_approval_makes_the_chat_wait_even_while_its_turn_is_in_flight() -> None:
    chat = _bare_chat("chat-state-3")

    assert _infer_session_state(chat, frozenset({"chat-state-3"}), frozenset({"chat-state-3"})) == "waiting_input"
    assert _infer_session_state(chat, frozenset(), frozenset({"chat-state-3"})) == "waiting_input"


def test_a_failing_compaction_streak_outranks_a_pending_approval_and_a_live_turn() -> None:
    chat = _bare_chat("chat-state-4", streak=4)

    assert _infer_session_state(chat, frozenset({"chat-state-4"}), frozenset({"chat-state-4"})) == "error"


def test_the_streak_a_person_requesting_compactions_can_reach_is_not_an_error() -> None:
    """A person's compactions stop counting at the guard limit, which stays below the streak that marks a chat as failing."""
    chat = _bare_chat("chat-state-5", streak=ANTI_THRASHING_STREAK_LIMIT)

    assert _infer_session_state(chat, frozenset(), frozenset()) == "ready"
