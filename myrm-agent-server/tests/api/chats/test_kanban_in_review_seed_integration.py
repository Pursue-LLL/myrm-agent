"""Integration test: IN_REVIEW seed fixture drives KanbanService (single writer).

The Chrome E2E relies on `POST /chats/test/seed-kanban-in-review-fixture` to
create an IN_REVIEW task without a second sqlite3 writer (which corrupted the
server's WAL). This test proves that chain at the API + service level: the
fixture creates the task through the real KanbanService/store, the task is
IN_REVIEW, and the badges API aggregates it — exactly the layer the E2E anchors.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.api.kanban.router import router as kanban_router
from app.services.kanban import KanbanService
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("chats", "statistics")
app.include_router(kanban_router, prefix="/api/v1")


@pytest.fixture(autouse=True)
def _reset_kanban_singleton() -> None:
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_kanban_agent_validation() -> None:
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture
def client(init_test_database) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _seed_visible_agent() -> None:
    """The seed fixture now binds tasks to an agent; provision one in the test DB."""
    from sqlalchemy import select

    from app.database.models.agent import Agent
    from app.platform_utils import get_session_factory

    async def _seed() -> None:
        session_factory = get_session_factory()
        async with session_factory() as db:
            existing = await db.scalar(
                select(Agent.id).where(Agent.id == "builtin-general")
            )
            if existing is not None:
                return
            db.add(
                Agent(
                    id="builtin-general",
                    name="General Agent",
                    model_selection={"model": "gpt-4o-mini"},
                ),
            )
            await db.commit()

    asyncio.run(_seed())


class TestKanbanInReviewSeedIntegration:
    def test_seed_creates_in_review_task_counted_by_badges(
        self, client: TestClient
    ) -> None:
        baseline = client.get("/api/v1/statistics/badges").json()["data"][
            "pendingApprovals"
        ]

        # The badge mixes goal-approval and kanban counts; assert on the kanban
        # increment directly so parallel suites' residual rows never skew it.
        async def _read_kanban_review_count() -> int:
            return await KanbanService.get_instance().count_tasks_by_status(
                TaskStatus.IN_REVIEW
            )

        before_kanban = asyncio.run(_read_kanban_review_count())

        with patch("app.api.chats.test_fixtures._kanban.is_local_mode", return_value=True):
            seed_resp = client.post("/api/v1/chats/test/seed-kanban-in-review-fixture")

        assert seed_resp.status_code == 200
        seed_body = seed_resp.json()
        board_id = str(seed_body["board_id"])
        task_id = str(seed_body["task_id"])
        task_title = str(seed_body["task_title"])
        assert board_id and task_id and task_title

        async def _assert_task_and_badges() -> None:
            kanban = KanbanService.get_instance()
            task = await kanban.get_task(task_id)
            assert task is not None
            assert task.title == task_title
            assert task.board_id == board_id
            assert task.status == TaskStatus.IN_REVIEW
            assert task.require_approval is True
            assert (
                await kanban.count_tasks_by_status(TaskStatus.IN_REVIEW)
                == before_kanban + 1
            )

        asyncio.run(_assert_task_and_badges())

        after = client.get("/api/v1/statistics/badges").json()["data"][
            "pendingApprovals"
        ]
        assert after == baseline + 1

    def test_seed_survives_approve_transition(self, client: TestClient) -> None:
        baseline = client.get("/api/v1/statistics/badges").json()["data"][
            "pendingApprovals"
        ]
        with patch("app.api.chats.test_fixtures._kanban.is_local_mode", return_value=True):
            seed_resp = client.post("/api/v1/chats/test/seed-kanban-in-review-fixture")
        task_id = str(seed_resp.json()["task_id"])

        assert (
            client.get("/api/v1/statistics/badges").json()["data"]["pendingApprovals"]
            == baseline + 1
        )

        approve_resp = client.post(
            f"/api/v1/kanban/tasks/{task_id}/approve", json={"approver": None}
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "completed"

        assert (
            client.get("/api/v1/statistics/badges").json()["data"]["pendingApprovals"]
            == baseline
        )

    def test_seed_survives_reject_transition(self, client: TestClient) -> None:
        baseline = client.get("/api/v1/statistics/badges").json()["data"][
            "pendingApprovals"
        ]
        with patch("app.api.chats.test_fixtures._kanban.is_local_mode", return_value=True):
            seed_resp = client.post("/api/v1/chats/test/seed-kanban-in-review-fixture")
        task_id = str(seed_resp.json()["task_id"])

        assert (
            client.get("/api/v1/statistics/badges").json()["data"]["pendingApprovals"]
            == baseline + 1
        )

        reject_resp = client.post(
            f"/api/v1/kanban/tasks/{task_id}/reject",
            json={"reason": "e2e reject"},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "ready"

        assert (
            client.get("/api/v1/statistics/badges").json()["data"]["pendingApprovals"]
            == baseline
        )
