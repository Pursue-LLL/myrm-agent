"""Tests for channel executor helper submodules."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.core.channel_bridge.executor_helpers.approval import (
    _timeout_decision,
    notify_channel_timeout_result,
    schedule_channel_approval_timeout,
)
from app.core.channel_bridge.executor_helpers.history import build_chat_history_with_metadata
from app.core.channel_bridge.executor_helpers.quick_replies import (
    extract_external_agents,
    suggest_quick_replies,
)
from app.core.types import ModelConfig
from app.services.chat.chat_helpers import ChannelHistoryEntry


@pytest.mark.asyncio
async def test_notify_channel_timeout_result_publishes_with_user_id() -> None:
    with patch(
        "app.core.channel_bridge.channel_gateway.publish",
        new_callable=AsyncMock,
    ) as mock_publish:
        await notify_channel_timeout_result(
            "telegram",
            "chat-42",
            "reject",
            "Done.",
            user_id="user-99",
        )

    mock_publish.assert_awaited_once()
    assert mock_publish.await_args is not None
    published = mock_publish.await_args.args[0]
    assert published.channel == "telegram"
    assert published.recipient_id == "chat-42"
    assert published.user_id == "user-99"
    assert "timed out" in published.content.lower()
    assert "Done." in published.content


@pytest.mark.asyncio
async def test_notify_channel_timeout_result_swallows_publish_errors() -> None:
    with patch(
        "app.core.channel_bridge.channel_gateway.publish",
        new_callable=AsyncMock,
        side_effect=RuntimeError("network down"),
    ):
        await notify_channel_timeout_result(
            "telegram",
            "chat-42",
            "approve",
            None,
            user_id="user-99",
        )


def test_schedule_channel_approval_timeout_registers_scheduler() -> None:
    mock_scheduler = MagicMock()
    params = MagicMock()

    with patch(
        "app.core.channel_bridge.executor_helpers.approval.ApprovalTimeoutScheduler.get",
        return_value=mock_scheduler,
    ):
        schedule_channel_approval_timeout(
            channel="telegram",
            peer="chat-1",
            chat_id="chat-db",
            timeout_info={"seconds": 120, "behavior": "deny"},
            params=params,
            user_id="user-1",
        )

    mock_scheduler.schedule.assert_called_once()
    call_kwargs = mock_scheduler.schedule.call_args.kwargs
    assert call_kwargs["key"] == "telegram:chat-1"
    assert call_kwargs["timeout_seconds"] == 120.0
    assert call_kwargs["behavior"] == "deny"
    assert callable(call_kwargs["resume_callback"])


def _channel_params() -> GeneralAgentParams:
    return GeneralAgentParams(
        query="deploy",
        model_cfg=ModelConfig(model="test/model", api_key="test-key"),
        channel_name="telegram",
    )


@contextmanager
def _patched_channel_resume(scheduler: ApprovalTimeoutScheduler | MagicMock, agent: MagicMock) -> Iterator[None]:
    """Run the channel timeout callback against a stand-in agent with every collaborator outside the helper replaced."""

    @asynccontextmanager
    async def credentials_scope(**_kwargs: object) -> AsyncIterator[None]:
        yield

    helper = "app.core.channel_bridge.executor_helpers.approval"
    with (
        patch(f"{helper}.ApprovalTimeoutScheduler.get", return_value=scheduler),
        patch(f"{helper}.load_history_without_persist", new=AsyncMock(return_value=("chat-db", []))),
        patch(f"{helper}.persist_assistant_message", new=AsyncMock()),
        patch(f"{helper}.notify_channel_timeout_result", new=AsyncMock()),
        patch.object(AgentFactory, "create_general_agent", return_value=agent),
        patch("app.services.agent.runtime_context.build_agent_runtime_context", new=AsyncMock(return_value={})),
        patch("app.services.agent.execution_cache.finalize_agent_session", new=AsyncMock()),
        patch(
            "app.services.agent.session_credential_assembler.user_config_session_credentials_scope",
            new=credentials_scope,
        ),
    ):
        yield


def _schedule_channel_timeout(params: GeneralAgentParams, timeout_seconds: float = 120) -> None:
    schedule_channel_approval_timeout(
        channel="telegram",
        peer="chat-1",
        chat_id="chat-db",
        timeout_info={"seconds": timeout_seconds, "behavior": "deny"},
        params=params,
        user_id="user-1",
    )


@pytest.mark.asyncio
async def test_channel_timeout_resume_runs_under_the_scheduler_key() -> None:
    """The channel turn suspended its graph under ``channel:peer``; resuming under another thread would find nothing."""
    scheduler = MagicMock()
    agent = MagicMock()

    async def stream(**_kwargs: object) -> AsyncIterator[dict[str, object]]:
        yield {"type": "message", "data": "Rejected, nothing deployed."}

    agent.process_stream = MagicMock(side_effect=stream)

    with _patched_channel_resume(scheduler, agent):
        _schedule_channel_timeout(_channel_params())
        resume_callback = scheduler.schedule.call_args.kwargs["resume_callback"]
        await resume_callback({"decision": "reject"})

    assert agent.approval_session_key == "telegram:chat-1"
    assert agent.process_stream.call_args.kwargs["query"].resume == {"decision": "reject"}
    scheduler.reopen.assert_not_called()


@pytest.mark.asyncio
async def test_channel_timeout_resume_that_dies_returns_the_claim_so_the_users_reply_is_accepted() -> None:
    """A timer that fired and then failed must not leave the approval answerable by nobody."""
    scheduler = ApprovalTimeoutScheduler()
    agent = MagicMock()
    failed = asyncio.Event()

    async def stream(**_kwargs: object) -> AsyncIterator[dict[str, object]]:
        failed.set()
        raise RuntimeError("provider unavailable")
        yield {}

    agent.process_stream = MagicMock(side_effect=stream)

    with _patched_channel_resume(scheduler, agent):
        _schedule_channel_timeout(_channel_params(), timeout_seconds=0.01)
        await asyncio.wait_for(failed.wait(), timeout=2)
        await asyncio.sleep(0.05)

    assert scheduler.resolve_if_first("telegram:chat-1") is True


@pytest.mark.asyncio
async def test_channel_timeout_resume_that_dies_before_streaming_returns_the_claim() -> None:
    scheduler = MagicMock()

    with _patched_channel_resume(scheduler, MagicMock()):
        _schedule_channel_timeout(_channel_params())
        resume_callback = scheduler.schedule.call_args.kwargs["resume_callback"]
        with (
            patch.object(AgentFactory, "create_general_agent", side_effect=RuntimeError("bad agent config")),
            pytest.raises(RuntimeError, match="bad agent config"),
        ):
            await resume_callback({"decision": "reject"})

    scheduler.reopen.assert_called_once_with("telegram:chat-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(("behavior", "expected"), [("allow", "approve"), ("deny", "reject")])
async def test_timeout_decision_reads_the_resume_value_the_scheduler_builds(behavior: str, expected: str) -> None:
    received: list[dict[str, object]] = []
    fired = asyncio.Event()

    async def capture(resume_value: dict[str, object]) -> None:
        received.append(resume_value)
        fired.set()

    ApprovalTimeoutScheduler().schedule("telegram:peer", 0.01, behavior, capture)
    await asyncio.wait_for(fired.wait(), timeout=2)

    assert _timeout_decision(received[0]) == expected


def test_build_chat_history_with_metadata_adds_timestamp_for_human() -> None:
    created = datetime(2026, 7, 13, 6, 0, tzinfo=timezone.utc)
    entries = [
        ChannelHistoryEntry(role="human", content="Hi", created_at=created),
        ChannelHistoryEntry(role="assistant", content="Hello", created_at=created),
    ]

    history = build_chat_history_with_metadata(entries)

    assert history == [
        ["human", "Hi", {"ts": "2026-07-13T06:00:00+00:00"}],
        ["assistant", "Hello"],
    ]


def test_extract_external_agents_returns_none_for_empty() -> None:
    assert extract_external_agents(None) is None
    assert extract_external_agents({}) is None


def test_extract_external_agents_returns_none_for_invalid_agents() -> None:
    assert extract_external_agents({"agents": "not-a-list"}) is None


def test_extract_external_agents_returns_agents_list() -> None:
    agents = [{"id": "a1"}]
    assert extract_external_agents({"agents": agents}) == agents


def test_suggest_quick_replies_only_on_first_message() -> None:
    first = suggest_quick_replies(is_first_message=True)
    later = suggest_quick_replies(is_first_message=False)
    assert len(first) > 0
    assert later == ()
