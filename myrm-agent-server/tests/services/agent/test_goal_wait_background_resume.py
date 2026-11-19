"""Goal WAIT resume after a background bash job finishes.

The keys and registry state are the production ones: the harness reports the session key of the run that started the
job (`chat_<chat id>`), the goal is stored under the chat id, and the finish arrives between turns, when no provider is
registered.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.agent.goals.wait_background_bash import WAIT_ON_BACKGROUND_JOB_ID_KEY
from myrm_agent_harness.api.hooks import BackgroundJobFinishResult
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.agent.goals.goal_wait_background_resume import maybe_resume_goal_after_background_job
from app.services.agent.params.workspace_resolve import chat_session_id

_JOB_ID = "a" * 32
_TRIGGER = "app.services.agent.goals.unattended.trigger_goal_stream_with_failure_policy"
_TRIGGER_STREAM = "app.services.agent.goals.unattended.trigger.trigger_goal_stream"
_NOTIFY = "app.services.agent.goals.unattended.failure.publish_goal_needs_review_notification"


@pytest.fixture(autouse=True)
def storage(tmp_path: Path) -> Iterator[None]:
    with patch("app.platform_utils.get_storage_provider", return_value=LocalStorageBackend(str(tmp_path))):
        yield


@pytest.fixture
def chat_id(request: pytest.FixtureRequest) -> str:
    return f"bg-wait-{request.node.name}"


def _finished(chat_id: str, job_id: str = _JOB_ID) -> BackgroundJobFinishResult:
    return BackgroundJobFinishResult(
        session_id=chat_session_id(chat_id),
        job_id=job_id,
        pid=4242,
        command="npm run build",
        status="exited",
        exit_code=0,
        error_category=None,
    )


async def _goal_waiting_on(chat_id: str, job_id: str) -> str:
    """A goal parked the way the harness parks one on a background job; returns its id."""
    provider = GoalRegistry.resolve_provider(chat_id)
    goal = await provider.create_goal(chat_id, "Build")
    await provider.enter_wait(goal.goal_id, reason=f"Waiting for background job {job_id}")
    await provider.update_metadata(goal.goal_id, {WAIT_ON_BACKGROUND_JOB_ID_KEY: job_id})
    return goal.goal_id


async def _status_of(chat_id: str, goal_id: str) -> GoalStatus:
    goal = await GoalRegistry.resolve_provider(chat_id).get_goal(goal_id)
    assert goal is not None
    return goal.status


@pytest.mark.asyncio
async def test_a_finished_job_ends_the_wait_of_its_chats_goal_and_starts_its_turn(chat_id: str) -> None:
    goal_id = await _goal_waiting_on(chat_id, _JOB_ID)

    with patch(_TRIGGER, new_callable=AsyncMock, return_value=True) as trigger:
        resumed = await maybe_resume_goal_after_background_job(_finished(chat_id))

    assert resumed is True
    assert await _status_of(chat_id, goal_id) is GoalStatus.ACTIVE
    trigger.assert_awaited_once()
    session, goal = trigger.await_args.args
    assert session == chat_id
    assert goal.goal_id == goal_id
    assert trigger.await_args.kwargs == {"context": "background wait resume"}
    assert GoalRegistry.get_provider(chat_id) is None


@pytest.mark.asyncio
async def test_a_job_the_goal_is_not_waiting_on_leaves_the_wait_alone(chat_id: str) -> None:
    goal_id = await _goal_waiting_on(chat_id, "b" * 32)

    with patch(_TRIGGER, new_callable=AsyncMock) as trigger:
        resumed = await maybe_resume_goal_after_background_job(_finished(chat_id))

    assert resumed is False
    assert await _status_of(chat_id, goal_id) is GoalStatus.WAIT
    trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_job_of_a_chat_without_a_goal_is_ignored(chat_id: str) -> None:
    with patch(_TRIGGER, new_callable=AsyncMock) as trigger:
        resumed = await maybe_resume_goal_after_background_job(_finished(chat_id))

    assert resumed is False
    trigger.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_start_of_the_resumed_turn_sends_the_goal_to_review(chat_id: str) -> None:
    goal_id = await _goal_waiting_on(chat_id, _JOB_ID)

    with (
        patch(_TRIGGER_STREAM, new_callable=AsyncMock, side_effect=RuntimeError("stream failed")),
        patch(_NOTIFY, new_callable=AsyncMock),
    ):
        resumed = await maybe_resume_goal_after_background_job(_finished(chat_id))

    assert resumed is False
    assert await _status_of(chat_id, goal_id) is GoalStatus.NEEDS_HUMAN_REVIEW
