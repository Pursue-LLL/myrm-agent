"""Every REST entry that stores or delivers instruction text a user typed refuses a secret in it, and stores nothing.

Runs the real route handlers; only the detection rules are injected. A refusal is HTTP 400 with the ``risk_held`` code and
the matched rules, so the web UI can name them; clean text and fields that are not prose still pass.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Protocol
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.api.agents.subagents import router as subagents_router
from app.api.background_tasks.router import router as background_tasks_router
from app.api.cron.routes import heartbeat_router, jobs_router
from app.api.cron.routes import helpers as cron_helpers
from app.api.kanban.router import router as kanban_router
from app.services.kanban import KanbanService
from app.services.risk.refusal import RISK_HELD_CODE
from tests.support.risk_gate import API_KEY_RULE, SECRET, build_service_with_rules

_DETECTION = "app.services.risk.detection.get_detection_service"


@pytest.fixture(autouse=True)
def _risk_rules() -> Iterator[None]:
    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        yield


class _HttpResponse(Protocol):
    """The part of a test client response these tests read; ``TestClient`` hands back whichever ``httpx`` it was built on."""

    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    def json(self) -> dict[str, dict[str, object]]: ...


def _assert_held(response: _HttpResponse) -> None:
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == RISK_HELD_CODE
    assert detail["rules"] == [{"rule_id": "r-apikey", "display_name": "API Key Leak", "severity": "critical"}]
    assert SECRET not in response.text


# --- subagent and background-task steering -----------------------------------------------------------------------


@pytest.fixture
def steer_client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(subagents_router, prefix="/chats")
    app.include_router(background_tasks_router, prefix="/background-tasks")
    with TestClient(app) as client:
        yield client


def test_subagent_steer_with_a_secret_never_reaches_the_child(steer_client: TestClient) -> None:
    manager = MagicMock()
    manager.steer_child.return_value = True

    with patch("app.api.agents.subagents.ACTIVE_SUBAGENTS", {"t-1": manager}):
        _assert_held(steer_client.post("/chats/c-1/subagents/t-1/steer", json={"message": f"use {SECRET}"}))

    manager.steer_child.assert_not_called()


def test_subagent_steer_with_clean_text_reaches_the_child(steer_client: TestClient) -> None:
    manager = MagicMock()
    manager.steer_child.return_value = True

    with patch("app.api.agents.subagents.ACTIVE_SUBAGENTS", {"t-1": manager}):
        response = steer_client.post("/chats/c-1/subagents/t-1/steer", json={"message": "only the 2026 rows"})

    assert response.status_code == 200
    manager.steer_child.assert_called_once_with("t-1", "only the 2026 rows")


def test_background_task_steer_with_a_secret_never_reaches_the_task(steer_client: TestClient) -> None:
    handler = MagicMock()
    handler.steer_background = AsyncMock(return_value=True)

    with patch("app.api.background_tasks.router.get_background_task_handler", return_value=handler):
        _assert_held(steer_client.post("/background-tasks/task-1/steer", json={"instruction": f"use {SECRET}"}))

    handler.steer_background.assert_not_awaited()


def test_background_task_steer_with_clean_text_reaches_the_task(steer_client: TestClient) -> None:
    handler = MagicMock()
    handler.steer_background = AsyncMock(return_value=True)

    with patch("app.api.background_tasks.router.get_background_task_handler", return_value=handler):
        response = steer_client.post("/background-tasks/task-1/steer", json={"instruction": "only the 2026 rows"})

    assert response.status_code == 200
    handler.steer_background.assert_awaited_once()


# --- cron jobs and heartbeat -------------------------------------------------------------------------------------


@pytest.fixture
def cron_client() -> Iterator[TestClient]:
    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=MagicMock(), config=CronConfig())
    manager = CronManager(store, scheduler, shell_enabled=True)
    app = FastAPI()
    app.include_router(jobs_router, prefix="/cron")
    app.include_router(heartbeat_router, prefix="/cron")
    with patch.object(cron_helpers, "_get_manager", return_value=manager), TestClient(app) as client:
        yield client


def _job(prompt: str) -> dict[str, object]:
    return {
        "name": "digest",
        "job_type": "agent",
        "schedule": {"kind": "interval", "interval_ms": 300_000},
        "prompt": prompt,
    }


def test_cron_job_prompt_with_a_secret_is_refused_and_not_stored(cron_client: TestClient) -> None:
    _assert_held(cron_client.post("/cron", json=_job(f"call the API with {SECRET}")))

    assert cron_client.get("/cron").json()["total"] == 0


def test_cron_job_with_a_clean_prompt_is_stored(cron_client: TestClient) -> None:
    assert cron_client.post("/cron", json=_job("check the stock")).status_code == 201


def test_cron_job_update_with_a_secret_prompt_is_refused_and_unchanged(cron_client: TestClient) -> None:
    job_id = cron_client.post("/cron", json=_job("check the stock")).json()["id"]

    _assert_held(cron_client.patch(f"/cron/{job_id}", json={"prompt": f"call the API with {SECRET}"}))

    assert cron_client.get(f"/cron/{job_id}").json()["prompt"] == "check the stock"


def test_cron_job_update_without_a_prompt_is_not_screened(cron_client: TestClient) -> None:
    """Changing the name must not re-screen, and so never block on, a prompt the user did not touch."""
    job_id = cron_client.post("/cron", json=_job("check the stock")).json()["id"]

    assert cron_client.patch(f"/cron/{job_id}", json={"name": "renamed"}).status_code == 200


def test_heartbeat_prompt_with_a_secret_is_refused_and_not_enabled(cron_client: TestClient) -> None:
    _assert_held(
        cron_client.post("/cron/heartbeat/enable", json={"interval_ms": 1_800_000, "prompt": f"ping {SECRET}"}),
    )

    assert cron_client.get("/cron/heartbeat/status").json()["enabled"] is False


def test_heartbeat_with_a_clean_prompt_is_enabled(cron_client: TestClient) -> None:
    response = cron_client.post("/cron/heartbeat/enable", json={"interval_ms": 1_800_000, "prompt": "check inbox"})

    assert response.status_code == 200
    assert response.json()["enabled"] is True


# --- kanban tasks and comments -----------------------------------------------------------------------------------


@pytest.fixture
def kanban_client() -> Iterator[TestClient]:
    KanbanService._instance = None
    app = FastAPI()
    app.include_router(kanban_router, prefix="/api/v1")
    with (
        patch.object(KanbanService, "_validate_agent_id", new_callable=AsyncMock),
        TestClient(app) as client,
    ):
        yield client
    KanbanService._instance = None


def _board(client: TestClient) -> str:
    return str(client.post("/api/v1/kanban/boards", json={"name": "Board"}).json()["board_id"])


def _task_count(client: TestClient, board_id: str) -> int:
    return len(client.get(f"/api/v1/kanban/boards/{board_id}/tasks").json()["items"])


@pytest.mark.parametrize(
    "fields",
    [
        {"title": f"deploy with {SECRET}"},
        {"title": "deploy", "description": f"use {SECRET}"},
        {"title": "deploy", "completion_criteria": f"done when {SECRET} works"},
        {"title": "deploy", "completion_criteria": [{"type": "semantic", "criteria": f"{SECRET} works"}]},
    ],
)
def test_kanban_task_with_a_secret_is_refused_and_not_stored(kanban_client: TestClient, fields: dict[str, object]) -> None:
    board_id = _board(kanban_client)

    _assert_held(kanban_client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json=fields))

    assert _task_count(kanban_client, board_id) == 0


def test_kanban_task_with_clean_text_and_a_shell_criterion_is_stored(kanban_client: TestClient) -> None:
    """A ``shell`` criterion is a command to run, not text a model reads, so it is not screened."""
    board_id = _board(kanban_client)

    response = kanban_client.post(
        f"/api/v1/kanban/boards/{board_id}/tasks",
        json={
            "title": "deploy",
            "description": "ship the release notes",
            "completion_criteria": [{"type": "shell", "command": f"curl -H 'x-key: {SECRET}' https://example.test"}],
        },
    )

    assert response.status_code == 201


@pytest.mark.parametrize("field", ["title", "description", "completion_criteria"])
def test_kanban_task_update_with_a_secret_is_refused_and_unchanged(kanban_client: TestClient, field: str) -> None:
    board_id = _board(kanban_client)
    task = kanban_client.post(
        f"/api/v1/kanban/boards/{board_id}/tasks",
        json={"title": "deploy", "description": "ship it", "completion_criteria": "tests pass"},
    ).json()

    _assert_held(kanban_client.patch(f"/api/v1/kanban/tasks/{task['task_id']}", json={field: f"use {SECRET}"}))

    current = kanban_client.get(f"/api/v1/kanban/tasks/{task['task_id']}").json()
    assert current["title"] == "deploy"
    assert current["description"] == "ship it"


def test_kanban_task_update_without_text_is_not_screened(kanban_client: TestClient) -> None:
    board_id = _board(kanban_client)
    task_id = kanban_client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json={"title": "deploy"}).json()["task_id"]

    assert kanban_client.patch(f"/api/v1/kanban/tasks/{task_id}", json={"priority": "high"}).status_code == 200


def _new_task(client: TestClient) -> str:
    return str(client.post(f"/api/v1/kanban/boards/{_board(client)}/tasks", json={"title": "deploy"}).json()["task_id"])


def _task_state(client: TestClient, task_id: str) -> dict[str, object]:
    state: dict[str, object] = client.get(f"/api/v1/kanban/tasks/{task_id}").json()
    return state


async def _set_status(task_id: str, status: TaskStatus) -> None:
    service = KanbanService.get_instance()
    task = await service.get_task(task_id)
    assert task is not None
    task.status = status
    await service.store.save_task(task)


def test_kanban_task_result_with_a_secret_is_refused_and_unchanged(kanban_client: TestClient) -> None:
    task_id = _new_task(kanban_client)

    _assert_held(kanban_client.patch(f"/api/v1/kanban/tasks/{task_id}", json={"result": f"deployed with {SECRET}"}))

    assert not _task_state(kanban_client, task_id)["result"]


def test_kanban_task_clean_result_is_stored(kanban_client: TestClient) -> None:
    task_id = _new_task(kanban_client)

    response = kanban_client.patch(f"/api/v1/kanban/tasks/{task_id}", json={"result": "deployed to staging"})

    assert response.status_code == 200
    assert _task_state(kanban_client, task_id)["result"] == "deployed to staging"


def test_kanban_reject_with_a_secret_is_refused_and_the_task_stays_in_review(kanban_client: TestClient) -> None:
    task_id = _new_task(kanban_client)
    asyncio.run(_set_status(task_id, TaskStatus.IN_REVIEW))

    _assert_held(kanban_client.post(f"/api/v1/kanban/tasks/{task_id}/reject", json={"reason": f"retry with {SECRET}"}))

    task = _task_state(kanban_client, task_id)
    assert task["status"] == "in_review"
    events = kanban_client.get(f"/api/v1/kanban/tasks/{task_id}/events").json()["items"]
    assert SECRET not in str(task) + str(events)


def test_kanban_reject_with_a_clean_reason_returns_the_task_to_ready(kanban_client: TestClient) -> None:
    task_id = _new_task(kanban_client)
    asyncio.run(_set_status(task_id, TaskStatus.IN_REVIEW))

    response = kanban_client.post(f"/api/v1/kanban/tasks/{task_id}/reject", json={"reason": "add source citations"})

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_kanban_reclaim_with_a_secret_is_refused_and_the_task_keeps_running(kanban_client: TestClient) -> None:
    task_id = _new_task(kanban_client)
    asyncio.run(_set_status(task_id, TaskStatus.RUNNING))

    _assert_held(kanban_client.post(f"/api/v1/kanban/tasks/{task_id}/reclaim", json={"reason": f"retry with {SECRET}"}))

    task = _task_state(kanban_client, task_id)
    assert task["status"] == "running"
    events = kanban_client.get(f"/api/v1/kanban/tasks/{task_id}/events").json()["items"]
    assert SECRET not in str(task) + str(events)


def test_kanban_reclaim_with_a_clean_reason_returns_the_task_to_ready(kanban_client: TestClient) -> None:
    task_id = _new_task(kanban_client)
    asyncio.run(_set_status(task_id, TaskStatus.RUNNING))

    response = kanban_client.post(f"/api/v1/kanban/tasks/{task_id}/reclaim", json={"reason": "stuck on the login page"})

    assert response.status_code == 200
    assert response.json()["task"]["status"] == "ready"


@pytest.mark.parametrize(
    "handoff",
    [
        {"result": f"done, key {SECRET}"},
        {"metadata": {"note": f"key {SECRET}"}},
        {"metadata": {"checks": {"env": ["A=1", f"KEY={SECRET}"]}}},
    ],
)
def test_kanban_move_with_a_secret_in_the_handoff_is_refused_and_not_moved(
    kanban_client: TestClient, handoff: dict[str, object]
) -> None:
    task_id = _new_task(kanban_client)
    before = _task_state(kanban_client, task_id)

    _assert_held(kanban_client.post(f"/api/v1/kanban/tasks/{task_id}/move", json={"status": "backlog", **handoff}))

    assert _task_state(kanban_client, task_id) == before


def test_kanban_move_with_a_clean_handoff_stores_it(kanban_client: TestClient) -> None:
    task_id = _new_task(kanban_client)

    response = kanban_client.post(
        f"/api/v1/kanban/tasks/{task_id}/move",
        json={"status": "backlog", "result": "parsed 3 files", "metadata": {"changed_files": ["a.py", "b.py"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "parsed 3 files"
    assert body["metadata"]["handoff"]["changed_files"] == ["a.py", "b.py"]


def test_kanban_comment_with_a_secret_is_refused_and_not_stored(kanban_client: TestClient) -> None:
    board_id = _board(kanban_client)
    task_id = kanban_client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json={"title": "deploy"}).json()["task_id"]

    _assert_held(kanban_client.post(f"/api/v1/kanban/tasks/{task_id}/comments", json={"body": f"key {SECRET}"}))

    events = kanban_client.get(f"/api/v1/kanban/tasks/{task_id}/events").json()["items"]
    assert SECRET not in str(events)


def test_kanban_clean_comment_is_stored(kanban_client: TestClient) -> None:
    board_id = _board(kanban_client)
    task_id = kanban_client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json={"title": "deploy"}).json()["task_id"]

    response = kanban_client.post(f"/api/v1/kanban/tasks/{task_id}/comments", json={"body": "looks good"})

    assert response.status_code == 201
