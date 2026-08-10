"""Nav badges API tests — GET /statistics/badges.

pendingApprovals combines goal-approval records with kanban IN_REVIEW tasks
awaiting human review, so the badge reflects every human-gated decision.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask, TaskStatus

from app.services.kanban import KanbanService
from tests.support.minimal_app import build_minimal_app

_app = build_minimal_app("statistics")


class TestNavBadges:
    def test_badges_include_kanban_review(self, monkeypatch) -> None:
        async def _fake_count(self, status: TaskStatus) -> int:
            return 3

        monkeypatch.setattr(KanbanService, "count_tasks_by_status", _fake_count)

        client = TestClient(_app)
        resp = client.get("/api/v1/statistics/badges")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["pendingApprovals"] == 3
        assert body["total"] == 3

    def test_badges_survive_missing_kanban(self, monkeypatch) -> None:
        from sqlalchemy.exc import OperationalError

        from app.services.kanban.service_mixins import query_dispatcher_mixin as qdm

        async def _boom(*args: object, **kwargs: object) -> None:
            raise OperationalError("stmt", {}, Exception("boom"))

        monkeypatch.setattr(qdm, "run_list_boards", _boom)

        client = TestClient(_app)
        resp = client.get("/api/v1/statistics/badges")
        assert resp.status_code == 200
        assert resp.json()["data"]["pendingApprovals"] == 0


class TestKanbanCountRealStore:
    """Real SQL store chain behind pendingApprovals.

    Verifies SqlAlchemyKanbanStore.count_tasks_by_agent grouping (agent_id x
    status, ARCHIVED excluded) and the KanbanService aggregation methods against
    actual rows — the layer previously only reachable via monkeypatch.
    """

    @pytest.fixture(autouse=True)
    def _reset_singleton(self) -> None:
        KanbanService._instance = None
        yield
        KanbanService._instance = None

    @pytest.mark.asyncio
    async def test_count_tasks_by_agent_real_sql(self) -> None:
        svc = KanbanService.get_instance()
        baseline = await svc.count_review_tasks_by_agent()

        board = await svc.store.save_board(KanbanBoard(board_id=str(uuid4()), name="Stat Board"))
        for task_id, agent_id, status in [
            ("t1", "agent-a", TaskStatus.IN_REVIEW),
            ("t2", None, TaskStatus.IN_REVIEW),
            ("t3", "agent-b", TaskStatus.COMPLETED),
            ("t4", "agent-a", TaskStatus.ARCHIVED),
        ]:
            await svc.store.save_task(
                KanbanTask(
                    task_id=task_id,
                    board_id=board.board_id,
                    title=task_id,
                    agent_id=agent_id,
                    status=status,
                )
            )

        grouped = await svc.store.count_tasks_by_agent(board.board_id)
        assert grouped["agent-a"] == {TaskStatus.IN_REVIEW.value: 1}
        assert grouped[None] == {TaskStatus.IN_REVIEW.value: 1}
        assert grouped["agent-b"] == {TaskStatus.COMPLETED.value: 1}
        assert await svc.store.count_tasks(board.board_id, status=TaskStatus.IN_REVIEW) == 2

        after = await svc.count_review_tasks_by_agent()
        assert after["agent-a"] == baseline.get("agent-a", 0) + 1
        assert after[None] == baseline.get(None, 0) + 1
