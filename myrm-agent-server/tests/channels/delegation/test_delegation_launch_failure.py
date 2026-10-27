"""A delegation whose receipt cannot be sent leaves nothing behind: no registered task, no quota slot.

Only the background run releases a user's quota slot, so a slot taken before a failing receipt send is lost for good and
two such failures lock the user out of ``/delegate`` until the service restarts. Runs on the real ``AgentRouter``.
"""

from __future__ import annotations

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.types import OutboundMessage
from tests.channels.delegation.test_delegation_router_control import _delegate, _hang, _router, _running, _until

_CHANNEL = "telegram"
_USER = "u1"


def _nothing_held(router: AgentRouter) -> bool:
    return not router._delegation_coordinator._tasks and router._delegation_guard.can_accept(_CHANNEL, _USER)


@pytest.mark.asyncio
async def test_a_receipt_that_cannot_be_sent_leaves_no_task_and_no_quota_slot() -> None:
    router, bus = _router(_hang)
    bus.publish_outbound.side_effect = ConnectionError("channel already gone")

    with pytest.raises(ConnectionError):
        await _delegate(router)

    assert _nothing_held(router)


@pytest.mark.asyncio
async def test_failed_receipts_never_use_up_the_quota() -> None:
    router, bus = _router(_hang)
    bus.publish_outbound.side_effect = ConnectionError("channel already gone")
    for _ in range(router._delegation_guard.max_active + 1):
        with pytest.raises(ConnectionError):
            await _delegate(router)

    bus.publish_outbound.side_effect = None
    await _delegate(router)

    try:
        await _until(lambda: _running(router) == 1)
    finally:
        await router.stop()


@pytest.mark.asyncio
async def test_the_receipt_is_sent_before_the_task_is_registered() -> None:
    router, bus = _router(_hang)
    held_when_sent: list[bool] = []

    async def record(msg: OutboundMessage, **_kwargs: object) -> None:
        held_when_sent.append(not _nothing_held(router))

    bus.publish_outbound.side_effect = record

    await _delegate(router)

    try:
        assert held_when_sent == [False]
        await _until(lambda: _running(router) == 1)
    finally:
        await router.stop()
