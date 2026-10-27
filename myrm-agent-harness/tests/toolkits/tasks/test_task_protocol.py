"""Tests for Task protocol and Task dataclass."""

import asyncio

from myrm_agent_harness.toolkits.tasks import (
    ErrorRecoverability,
    RetryPolicy,
    Task,
    TaskError,
    TaskStatus,
)


def test_task_creation():
    """Test Task dataclass creation."""
    task = Task(
        task_id="test-001",
        task_type="image_generate",
        user_id="user-123",
        status=TaskStatus.PENDING,
        payload={"prompt": "a cat"},
        priority=5,
        timeout=300,
    )

    assert task.task_id == "test-001"
    assert task.task_type == "image_generate"
    assert task.status == TaskStatus.PENDING
    assert task.payload == {"prompt": "a cat"}
    assert task.priority == 5
    assert task.timeout == 300


def test_task_is_terminal():
    """Test Task.is_terminal()."""
    pending_task = Task(
        task_id="t1",
        task_type="test",
        user_id="u1",
        status=TaskStatus.PENDING,
        payload={},
    )
    assert not pending_task.is_terminal()

    succeeded_task = Task(
        task_id="t2",
        task_type="test",
        user_id="u1",
        status=TaskStatus.SUCCEEDED,
        payload={},
    )
    assert succeeded_task.is_terminal()

    failed_task = Task(
        task_id="t3",
        task_type="test",
        user_id="u1",
        status=TaskStatus.FAILED,
        payload={},
    )
    assert failed_task.is_terminal()

    cancelled_task = Task(
        task_id="t4",
        task_type="test",
        user_id="u1",
        status=TaskStatus.CANCELLED,
        payload={},
    )
    assert cancelled_task.is_terminal()


def test_task_can_retry():
    """Test Task.can_retry()."""
    task = Task(
        task_id="t1",
        task_type="test",
        user_id="u1",
        status=TaskStatus.FAILED,
        payload={},
        retry_policy=RetryPolicy(max_retries=3),
        retry_count=2,
    )
    assert task.can_retry()

    task.retry_count = 3
    assert not task.can_retry()

    task_no_policy = Task(
        task_id="t2",
        task_type="test",
        user_id="u1",
        status=TaskStatus.FAILED,
        payload={},
        retry_count=0,
    )
    assert not task_no_policy.can_retry()


def test_task_is_active():
    """Test Task.is_active()."""
    queued = Task("t1", "test", "u1", TaskStatus.QUEUED, {})
    running = Task("t2", "test", "u1", TaskStatus.RUNNING, {})
    pending = Task("t3", "test", "u1", TaskStatus.PENDING, {})
    assert queued.is_active()
    assert running.is_active()
    assert not pending.is_active()


def test_task_can_retry_requires_failed_status():
    """can_retry() is False unless status is FAILED."""
    task = Task(
        task_id="t1",
        task_type="test",
        user_id="u1",
        status=TaskStatus.RUNNING,
        payload={},
        retry_policy=RetryPolicy(max_retries=3),
        retry_count=0,
    )
    assert not task.can_retry()


def test_task_can_retry_permanent_error():
    """Permanent errors are not retryable."""
    task = Task(
        task_id="t1",
        task_type="test",
        user_id="u1",
        status=TaskStatus.FAILED,
        payload={},
        retry_policy=RetryPolicy(max_retries=3),
        retry_count=0,
        error=TaskError(
            error_type="validation_error",
            message="bad prompt",
            recoverable=ErrorRecoverability.PERMANENT,
        ),
    )
    assert not task.can_retry()


def test_task_cancellation_event():
    """Test Task cancellation event."""
    event = asyncio.Event()
    Task(
        task_id="t1",
        task_type="test",
        user_id="u1",
        status=TaskStatus.RUNNING,
        payload={},
        cancellation_event=event,
    )

    assert not event.is_set()
    event.set()
    assert event.is_set()


def test_retry_policy():
    """Test RetryPolicy."""
    policy = RetryPolicy(
        max_retries=3,
        base_delay=1.0,
        max_delay=60.0,
        exponential_base=2.0,
    )

    assert policy.get_delay(0) == 1.0
    assert policy.get_delay(1) == 2.0
    assert policy.get_delay(2) == 4.0
    assert policy.get_delay(10) == 60.0

    policy_linear = RetryPolicy(
        max_retries=3,
        base_delay=5.0,
        exponential_base=1.0,  # No exponential growth
    )
    assert policy_linear.get_delay(1) == 5.0
    assert policy_linear.get_delay(2) == 5.0
