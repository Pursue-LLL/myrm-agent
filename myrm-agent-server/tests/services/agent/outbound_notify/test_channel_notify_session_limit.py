"""Session limit of channel_notify_tool while sends are in flight or failing.

A model can emit several tool calls in one turn and the agent loop runs them concurrently, so the limit has to hold
while earlier sends are still in flight; a failed send has taken its slot as well.
"""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.tools import BaseTool

from app.channels.types.messages import MediaAttachment
from app.services.agent.outbound_notify import (
    NotifyResult,
    NotifyTarget,
    NotifyToolConfig,
    create_channel_notify_tool,
)

DESTINATION = "telegram:Team"
LIMIT = 3


class SuspendingSender:
    """A sender whose delivery yields to the event loop, as a real network send does."""

    def __init__(self, *, succeeds: bool = True) -> None:
        self.attempts = 0
        self._succeeds = succeeds

    async def send(
        self,
        target: NotifyTarget,
        body: str,
        media: tuple[MediaAttachment, ...] = (),
    ) -> NotifyResult:
        await asyncio.sleep(0)
        self.attempts += 1
        if self._succeeds:
            return NotifyResult(success=True, channel=target.channel)
        return NotifyResult(success=False, channel=target.channel, error="delivery failed")


def _notify_tool(sender: SuspendingSender) -> BaseTool:
    config = NotifyToolConfig(
        destinations={DESTINATION: NotifyTarget(channel="telegram", recipient_id="chat_1")},
        rate_limit_per_session=LIMIT,
    )
    return create_channel_notify_tool(sender, config)


async def _notify(tool: BaseTool, index: int) -> str:
    return str(await tool.ainvoke({"destination": DESTINATION, "body": f"message {index}"}))


async def _notify_in_parallel(tool: BaseTool, calls: int) -> list[str]:
    return list(await asyncio.gather(*(_notify(tool, index) for index in range(calls))))


@pytest.mark.asyncio
async def test_parallel_calls_beyond_the_limit_are_rejected() -> None:
    sender = SuspendingSender()

    outcomes = await _notify_in_parallel(_notify_tool(sender), LIMIT + 2)

    assert sender.attempts == LIMIT
    assert sum("rate limit" in outcome.lower() for outcome in outcomes) == 2


@pytest.mark.asyncio
async def test_parallel_calls_within_the_limit_are_all_delivered() -> None:
    sender = SuspendingSender()

    outcomes = await _notify_in_parallel(_notify_tool(sender), LIMIT)

    assert sender.attempts == LIMIT
    assert all("success" in outcome.lower() for outcome in outcomes)


@pytest.mark.asyncio
async def test_failed_sends_use_the_limit_too() -> None:
    sender = SuspendingSender(succeeds=False)
    tool = _notify_tool(sender)

    for index in range(LIMIT):
        assert "delivery failed" in await _notify(tool, index)
    outcome = await _notify(tool, LIMIT)

    assert "rate limit" in outcome.lower()
    assert sender.attempts == LIMIT
