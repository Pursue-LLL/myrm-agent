"""Real full-chain integration tests for pendingApprovals (kanban IN_REVIEW).

Seeds kanban rows through the real SqlAlchemyKanbanStore, then asserts the
badges and fleet-overview APIs reflect actual counts. The counting chain
(KanbanService aggregation → store SQL) is never mocked; only real data flows
end-to-end. Incremental assertions immunize against residual rows from
parallel test suites sharing the test database.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask, TaskStatus

from app.services.kanban import KanbanService
from tests.support.minimal_app import build_minimal_app


@pytest.mark.integration
class TestPendingApprovalsFullChain:
    """Badges + fleet KPIs reflect real kanban IN_REVIEW rows end-to-end."""

    @pytest.fixture(autouse=True)
    def _reset_singleton(self) -> None:
        KanbanService._instance = None
        yield
        KanbanService._instance = None

    @pytest.mark.asyncio
    async def test_badges_and_fleet_reflect_real_kanban_review(self) -> None:
        client = TestClient(build_minimal_app("statistics", "fleet_overview"))

        before_badges = client.get("/api/v1/statistics/badges").json()["data"]["pendingApprovals"]
        before_fleet = client.get("/api/v1/agents/fleet-overview").json()["data"]["kpi"]["pendingApprovals"]

        svc = KanbanService.get_instance()
        board = await svc.store.save_board(
            KanbanBoard(board_id=str(uuid4()), name="Full Chain Board")
        )
        await svc.store.save_task(
            KanbanTask(
                task_id=str(uuid4()),
                board_id=board.board_id,
                title="Needs approval",
                agent_id="agent-x",
                status=TaskStatus.IN_REVIEW,
            )
        )

        after_badges = client.get("/api/v1/statistics/badges").json()["data"]["pendingApprovals"]
        assert after_badges == before_badges + 1

        fleet_body = client.get("/api/v1/agents/fleet-overview").json()["data"]
        assert fleet_body["kpi"]["pendingApprovals"] == before_fleet + 1
        assert fleet_body["agents"]["agent-x"]["pendingApprovals"] >= 1
