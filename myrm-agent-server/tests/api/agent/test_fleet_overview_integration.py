"""Fleet Overview API integration tests — full DB round-trip, no mocks on data path.

Validates GET /api/v1/agents/fleet-overview returns correct per-agent
aggregations from Chat, CronJobModel, and ApprovalRecord tables.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import Base, Chat
from app.database.models.approval import ApprovalRecord
from app.database.models.cron import CronJobModel
from tests.support.minimal_app import build_minimal_app

_app = build_minimal_app("fleet_overview", "user_agents")

AGENT_A = "agent-alpha"
AGENT_B = "agent-beta"


@pytest.fixture
async def db_session(tmp_path):
    db_file = tmp_path / "fleet_test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    from app.database.connection import get_db

    _app.dependency_overrides[get_db] = override_get_db

    async with session_factory() as session:
        yield session

    _app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def client(db_session) -> TestClient:
    return TestClient(_app)


async def _seed_chats(db: AsyncSession, agent_id: str, count: int, tokens: int = 100) -> None:
    now = datetime.now(UTC)
    for _ in range(count):
        chat = Chat(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            total_tokens=tokens,
            total_usd=tokens * 0.00001,
            total_calls=1,
            created_at=now - timedelta(hours=1),
        )
        db.add(chat)
    await db.commit()


async def _seed_cron_jobs(db: AsyncSession, agent_id: str, active: int, inactive: int = 0) -> None:
    schedule = {"kind": "cron", "expr": "0 8 * * *"}
    for _ in range(active):
        job = CronJobModel(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            name="test-cron",
            prompt="test",
            job_type="agent",
            schedule=schedule,
            status="active",
        )
        db.add(job)
    for _ in range(inactive):
        job = CronJobModel(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            name="paused-cron",
            prompt="test",
            job_type="agent",
            schedule=schedule,
            status="paused",
        )
        db.add(job)
    await db.commit()


async def _seed_approvals(db: AsyncSession, agent_id: str, pending: int, resolved: int = 0) -> None:
    for _ in range(pending):
        record = ApprovalRecord(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            chat_id=str(uuid.uuid4()),
            action_type="shell_command",
            payload={"command": "echo test"},
            status="PENDING",
        )
        db.add(record)
    for _ in range(resolved):
        record = ApprovalRecord(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            chat_id=str(uuid.uuid4()),
            action_type="shell_command",
            payload={"command": "echo test"},
            status="APPROVED",
        )
        db.add(record)
    await db.commit()


class TestFleetOverviewAPI:
    """Full DB round-trip tests for /agents/fleet-overview."""

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_kpi(self, client: TestClient, db_session: AsyncSession) -> None:
        resp = client.get("/api/v1/agents/fleet-overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

        kpi = body["data"]["kpi"]
        assert kpi["onlineAgents"] == 0
        assert kpi["monthTokens"] == 0
        assert kpi["monthCost"] == 0.0
        assert kpi["pendingApprovals"] == 0
        assert body["data"]["agents"] == {}

    @pytest.mark.asyncio
    async def test_single_agent_stats(self, client: TestClient, db_session: AsyncSession) -> None:
        await _seed_chats(db_session, AGENT_A, count=3, tokens=500)
        await _seed_cron_jobs(db_session, AGENT_A, active=2, inactive=1)
        await _seed_approvals(db_session, AGENT_A, pending=1, resolved=2)

        resp = client.get("/api/v1/agents/fleet-overview")
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]

        assert AGENT_A in data["agents"]
        stats = data["agents"][AGENT_A]
        assert stats["sessionCount"] == 3
        assert stats["monthTokens"] == 1500
        assert stats["cronCount"] == 2
        assert stats["pendingApprovals"] == 1
        assert stats["status"] == "idle"

        assert data["kpi"]["monthTokens"] == 1500
        assert data["kpi"]["pendingApprovals"] == 1

    @pytest.mark.asyncio
    async def test_multi_agent_aggregation(self, client: TestClient, db_session: AsyncSession) -> None:
        await _seed_chats(db_session, AGENT_A, count=2, tokens=1000)
        await _seed_chats(db_session, AGENT_B, count=5, tokens=200)
        await _seed_approvals(db_session, AGENT_A, pending=3)
        await _seed_approvals(db_session, AGENT_B, pending=1)

        resp = client.get("/api/v1/agents/fleet-overview")
        body = resp.json()["data"]

        assert body["agents"][AGENT_A]["sessionCount"] == 2
        assert body["agents"][AGENT_A]["monthTokens"] == 2000
        assert body["agents"][AGENT_B]["sessionCount"] == 5
        assert body["agents"][AGENT_B]["monthTokens"] == 1000

        assert body["kpi"]["monthTokens"] == 3000
        assert body["kpi"]["pendingApprovals"] == 4

    @pytest.mark.asyncio
    async def test_inactive_crons_not_counted(self, client: TestClient, db_session: AsyncSession) -> None:
        await _seed_cron_jobs(db_session, AGENT_A, active=1, inactive=3)

        resp = client.get("/api/v1/agents/fleet-overview")
        stats = resp.json()["data"]["agents"][AGENT_A]
        assert stats["cronCount"] == 1

    @pytest.mark.asyncio
    async def test_resolved_approvals_not_counted(self, client: TestClient, db_session: AsyncSession) -> None:
        await _seed_approvals(db_session, AGENT_A, pending=0, resolved=5)

        resp = client.get("/api/v1/agents/fleet-overview")
        body = resp.json()["data"]
        if AGENT_A in body["agents"]:
            assert body["agents"][AGENT_A]["pendingApprovals"] == 0
        assert body["kpi"]["pendingApprovals"] == 0

    @pytest.mark.asyncio
    async def test_default_agent_key_for_null_agent_id(self, client: TestClient, db_session: AsyncSession) -> None:
        await _seed_chats(db_session, None, count=2, tokens=100)

        resp = client.get("/api/v1/agents/fleet-overview")
        body = resp.json()["data"]
        assert "default" in body["agents"]
        assert body["agents"]["default"]["sessionCount"] == 2
