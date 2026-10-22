"""The agent run an approval timeout resumes counts as in flight while it executes, and always releases."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent.run_activity import active_background_agent_runs
from app.core.channel_bridge.executor_helpers.approval import schedule_channel_approval_timeout

_APPROVAL = "app.core.channel_bridge.executor_helpers.approval"


class _FakeParams:
    agent_id = "main"
    query: object = None

    def model_copy(self) -> _FakeParams:
        return _FakeParams()


class _FakeAgent:
    def __init__(self, *, fail: bool) -> None:
        self.observed: list[int] = []
        self._fail = fail

    async def process_stream(self, **_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        self.observed.append(active_background_agent_runs())
        if self._fail:
            raise RuntimeError("agent crashed")
        yield {"type": "message", "data": "done"}


@asynccontextmanager
async def _credentials_scope(*, channel: str) -> AsyncIterator[None]:
    yield


async def _resume(agent: _FakeAgent) -> None:
    """Schedule the timeout guard, capture its resume callback, and run it."""
    scheduler = MagicMock()
    with (
        patch(f"{_APPROVAL}.ApprovalTimeoutScheduler") as scheduler_cls,
        patch("app.ai_agents.agents.GeneralAgentParams", _FakeParams),
        patch("app.ai_agents.agents.AgentFactory.create_general_agent", return_value=agent),
        patch("app.services.agent.runtime_context.build_agent_runtime_context", AsyncMock(return_value={})),
        patch("app.services.agent.execution_cache.finalize_agent_session", AsyncMock()),
        patch(
            "app.services.agent.session_credential_assembler.user_config_session_credentials_scope",
            _credentials_scope,
        ),
        patch(f"{_APPROVAL}.load_history_without_persist", AsyncMock(return_value=(None, []))),
        patch(f"{_APPROVAL}.build_chat_history_with_metadata", MagicMock(return_value=[])),
        patch(f"{_APPROVAL}.persist_assistant_message", AsyncMock()),
        patch(f"{_APPROVAL}.notify_channel_timeout_result", AsyncMock()),
    ):
        scheduler_cls.get.return_value = scheduler
        schedule_channel_approval_timeout(
            "telegram",
            "peer-1",
            "chat-1",
            {"seconds": 300, "behavior": "deny"},
            _FakeParams(),
            user_id="user-1",
        )
        resume_callback = scheduler.schedule.call_args.kwargs["resume_callback"]
        await resume_callback({"decision": "reject"})


@pytest.mark.asyncio
async def test_timeout_resume_counts_while_the_agent_runs_and_releases() -> None:
    agent = _FakeAgent(fail=False)
    baseline = active_background_agent_runs()

    await _resume(agent)

    assert agent.observed == [baseline + 1]
    assert active_background_agent_runs() == baseline


@pytest.mark.asyncio
async def test_timeout_resume_is_released_when_the_agent_fails() -> None:
    agent = _FakeAgent(fail=True)
    baseline = active_background_agent_runs()

    with pytest.raises(RuntimeError, match="agent crashed"):
        await _resume(agent)

    assert agent.observed == [baseline + 1]
    assert active_background_agent_runs() == baseline
