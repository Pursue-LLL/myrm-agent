"""Integration tests for Task Timeline and Mid-Flight Interrupt API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.tasks.timeline_router import router as timeline_router
from app.services.observability.timeline import TaskTimelineInspectorService
from myrm_agent_harness.observability.timeline_visualizer import TimelineIOMetrics


@pytest.fixture(scope="function")
def client() -> TestClient:
    test_app = FastAPI(title="Task Timeline Test App")
    test_app.include_router(timeline_router, prefix="/api/v1/tasks")
    return TestClient(test_app, raise_server_exceptions=False)


def test_get_task_timeline_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/tasks/task_empty_001/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "task_empty_001"
    assert data["tree"] == []
    assert data["waterfall"] == []
    assert data["summary"]["total_steps"] == 0


def test_get_task_timeline_with_steps(client: TestClient) -> None:
    task_id = "task_exec_100"
    service = TaskTimelineInspectorService.get_instance()

    root_id = service.record_step(
        task_id=task_id,
        step_name="DecomposePrompt",
        node_type="agent_thought",
        input_payload={"prompt": "build web app"},
    )

    child_id = service.record_step(
        task_id=task_id,
        step_name="ScaffoldReactApp",
        node_type="tool_invocation",
        parent_id=root_id,
        input_payload={"framework": "vite"},
    )

    service.complete_step(
        task_id=task_id,
        node_id=child_id,
        output_payload={"status": "created"},
        metrics=TimelineIOMetrics(
            input_chars=50,
            output_chars=200,
            prompt_tokens=25,
            completion_tokens=80,
            cache_hit=True,
        ),
    )

    resp = client.get(f"/api/v1/tasks/{task_id}/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == task_id
    assert len(data["tree"]) == 1
    assert data["tree"][0]["step_name"] == "DecomposePrompt"
    assert len(data["tree"][0]["children"]) == 1
    assert data["tree"][0]["children"][0]["step_name"] == "ScaffoldReactApp"
    assert data["tree"][0]["children"][0]["status"] == "completed"
    assert data["tree"][0]["children"][0]["metrics"]["cache_hit"] is True

    assert data["summary"]["total_steps"] == 2
    assert data["summary"]["completed_steps"] == 1
    assert data["summary"]["running_steps"] == 1


def test_interrupt_task_barge_in(client: TestClient) -> None:
    task_id = "task_interrupt_200"
    service = TaskTimelineInspectorService.get_instance()

    service.record_step(
        task_id=task_id,
        step_name="LongRunningScrape",
        node_type="tool_invocation",
    )

    interrupt_payload = {
        "reason": "user_correction",
        "instruction": "Please stop scraping and use existing cache instead.",
    }

    resp = client.post(f"/api/v1/tasks/{task_id}/interrupt", json=interrupt_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == task_id
    assert data["status"] == "interrupted"
    assert data["interrupted_steps_count"] == 1
    assert data["instruction"] == "Please stop scraping and use existing cache instead."

    # Verify timeline reflects the interruption
    timeline_resp = client.get(f"/api/v1/tasks/{task_id}/timeline")
    assert timeline_resp.status_code == 200
    timeline_data = timeline_resp.json()
    assert timeline_data["summary"]["interrupted_steps"] == 1
    assert len(timeline_data["interruptions"]) == 1
    assert timeline_data["interruptions"][0]["reason"] == "user_correction"
