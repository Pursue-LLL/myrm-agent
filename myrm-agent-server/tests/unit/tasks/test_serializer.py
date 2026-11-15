from __future__ import annotations

from datetime import datetime, timezone

from myrm_agent_harness.toolkits.tasks import (
    ErrorRecoverability,
    Task,
    TaskError,
    TaskStatus,
)

from app.tasks.serializer import serialize_media_task


def test_serialize_media_task_non_task_returns_empty():
    assert serialize_media_task(None) == {}
    assert serialize_media_task("not-a-task") == {}
    assert serialize_media_task({"task_id": "123"}) == {}


def test_serialize_media_task_minimal_task():
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    task = Task(
        task_id="task-123",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "cat"},
        created_at=now,
        updated_at=now,
    )
    res = serialize_media_task(task)
    assert res["task_id"] == "task-123"
    assert res["task_type"] == "image_generate"
    assert res["status"] == "pending"
    assert res["result"] is None
    assert res["error"] is None
    assert res["started_at"] is None
    assert res["completed_at"] is None
    assert res["created_at"] == now.isoformat()


def test_serialize_media_task_with_error_and_timestamps():
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    task = Task(
        task_id="task-err",
        task_type="video_generate",
        user_id="user-1",
        status=TaskStatus.FAILED,
        payload={"prompt": "sunset"},
        error=TaskError(
            error_type="generation_failed",
            message="GPU out of memory",
            recoverable=ErrorRecoverability.TRANSIENT,
        ),
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    res = serialize_media_task(task)
    assert res["status"] == "failed"
    assert res["error"] == {
        "error_type": "generation_failed",
        "message": "GPU out of memory",
        "recoverable": "transient",
    }
    assert res["started_at"] == now.isoformat()
    assert res["completed_at"] == now.isoformat()


def test_serialize_media_task_failed_task_carries_next_step():
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    task = Task(
        task_id="task-failed",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.FAILED,
        payload={"prompt": "cat"},
        error=TaskError(
            error_type="ImageGenerationError",
            message="Your request was rejected by the safety system",
            recoverable=ErrorRecoverability.TRANSIENT,
        ),
        created_at=now,
        updated_at=now,
    )
    next_step = serialize_media_task(task)["next_step"]
    assert isinstance(next_step, str)
    assert "do not reword the prompt to get around it" in next_step
    assert "retry at most once" in next_step


def test_serialize_media_task_only_failed_tasks_carry_next_step():
    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    for status in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.SUCCEEDED, TaskStatus.CANCELLED):
        task = Task(
            task_id=f"task-{status.value}",
            task_type="image_generate",
            user_id="user-1",
            status=status,
            payload={"prompt": "cat"},
            created_at=now,
            updated_at=now,
        )
        assert "next_step" not in serialize_media_task(task), status
