"""A delegated run waits for a tool approval as long as the task itself may run.

The requester of a delegated task is not watching the chat, so the configured approval window (minutes) would deny the
tool before they ever see the request. The coordinator hands the task's time limit to the run through the message, and
the security config of that turn carries it to the harness, which bounds it.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import pytest
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config

from app.channels.delegation import DelegationCoordinator, build_delegation_task
from app.channels.types import METADATA_APPROVAL_WINDOW_SECONDS_KEY, InboundMessage, OutboundMessage
from app.core.channel_bridge.agent_executor.execute_preamble.types import build_security_config
from tests.channels.delegation.test_delegation_router_control import _APPROVE, _delegate, _inbound, _router, _until


@dataclass
class _Bus:
    published: list[OutboundMessage] = field(default_factory=list)

    async def publish_outbound(self, message: OutboundMessage) -> None:
        self.published.append(message)


class _RecordingExecutor:
    """Records the message the delegated run starts from."""

    def __init__(self) -> None:
        self.seen: list[InboundMessage] = []

    async def execute_stream(self, msg: InboundMessage, *_args: object, **_kwargs: object) -> AsyncGenerator[object, None]:
        self.seen.append(msg)
        return
        yield


async def _hand_over(_request: object) -> None:
    return None


def _approval_wait(metadata: dict[str, object], *, configured: int = 120, agent_profile: dict[str, object] | None = None) -> int:
    """The approval wait the harness ends up with for a turn: the production path from message metadata to SecurityConfig."""
    raw = build_security_config({"approvalTimeoutSeconds": configured}, metadata)
    effective = build_channel_security_config(
        "telegram",
        raw,
        agent_security_raw=agent_profile or {},
        declared_capabilities=(),
        declared_allowed_roots=(),
        local_mode=True,
        privacy_policy=None,
    )
    return effective.approval_timeout_seconds


def _requester_message() -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        chat_id="chat-1",
        content="/delegate do the report",
        user_id="user-1",
        metadata={"locale": "en"},
    )


async def _run_delegated(timeout_seconds: float) -> tuple[InboundMessage, InboundMessage]:
    """Run one delegated task; returns (the requester's message, the message the run started from)."""
    coordinator = DelegationCoordinator()
    task = build_delegation_task("telegram", "user-1", "chat-1", "do the report", timeout_seconds=timeout_seconds)
    coordinator.register_task(task)
    executor = _RecordingExecutor()
    requester = _requester_message()

    await coordinator.execute_task_lifecycle(
        task,
        executor,  # type: ignore[arg-type]
        _Bus(),  # type: ignore[arg-type]
        requester,
        hand_over_approval=_hand_over,
    )

    assert len(executor.seen) == 1
    return requester, executor.seen[0]


@pytest.mark.asyncio
async def test_the_run_starts_from_a_message_that_carries_the_task_time_limit() -> None:
    _requester, run_msg = await _run_delegated(timeout_seconds=1800.0)

    assert run_msg.content == "do the report"
    assert run_msg.metadata[METADATA_APPROVAL_WINDOW_SECONDS_KEY] == 1800.0
    assert run_msg.metadata["locale"] == "en"


@pytest.mark.asyncio
async def test_the_requesters_own_message_is_left_untouched() -> None:
    requester, _run_msg = await _run_delegated(timeout_seconds=1800.0)

    assert METADATA_APPROVAL_WINDOW_SECONDS_KEY not in requester.metadata
    assert requester.content == "/delegate do the report"


@pytest.mark.asyncio
@pytest.mark.parametrize(("task_limit", "waits"), [(1800.0, 1800), (3600.0, 3600), (7200.0, 3600)])
async def test_the_harness_waits_for_the_task_limit_up_to_its_own_ceiling(task_limit: float, waits: int) -> None:
    _requester, run_msg = await _run_delegated(timeout_seconds=task_limit)

    assert _approval_wait(run_msg.metadata) == waits


@pytest.mark.asyncio
async def test_a_wait_the_agent_profile_sets_explicitly_still_wins() -> None:
    _requester, run_msg = await _run_delegated(timeout_seconds=1800.0)

    assert _approval_wait(run_msg.metadata, agent_profile={"approvalTimeoutSeconds": 45}) == 45


@pytest.mark.asyncio
async def test_a_foreground_turn_keeps_the_configured_window() -> None:
    assert _approval_wait(_requester_message().metadata, configured=90) == 90


@pytest.mark.asyncio
async def test_the_run_the_chats_answer_resumes_asks_again_with_the_configured_window() -> None:
    seen: list[InboundMessage] = []

    async def stream(msg: InboundMessage, *_args: object, **_kwargs: object) -> AsyncGenerator[object, None]:
        seen.append(msg)
        yield _APPROVE

    router, bus = _router(stream)
    await _delegate(router)
    await _until(lambda: bus.send_tracked.call_count == 1)

    await router._handle_approval_command(_inbound("/approve"), "allow_once")

    resume = router._gate.submit.call_args.args[0]  # type: ignore[attr-defined]
    assert METADATA_APPROVAL_WINDOW_SECONDS_KEY in seen[0].metadata
    assert METADATA_APPROVAL_WINDOW_SECONDS_KEY not in resume.metadata
