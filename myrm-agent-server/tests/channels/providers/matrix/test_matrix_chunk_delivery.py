"""Matrix text delivery through the real retry layer: a part that fails is retried alone, never the whole reply."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.matrix import MatrixChannel
from app.channels.reliability.retry import RetryConfig, send_with_retry
from app.channels.types import ChannelStatus, OutboundMessage

_PARTS = ["part1", "part2", "part3", "part4", "part5"]


def _channel(*, failing_part: str, failures: int) -> tuple[MatrixChannel, list[str]]:
    """A Matrix channel whose homeserver refuses ``failing_part`` ``failures`` times; second item is the room log."""
    ch = MatrixChannel(homeserver="https://matrix.test.com", access_token="tok")
    ch.retry_config = RetryConfig(max_retries=3, base_delay=0.0, max_delay=0.0, jitter=0.0)
    ch._client = MagicMock()
    ch._status = ChannelStatus.RUNNING
    ch._get_room_members = AsyncMock(return_value={})  # type: ignore[method-assign]
    room: list[str] = []
    refused = 0

    async def post(client: object, room_id: str, content: dict[str, object]) -> str | None:
        nonlocal refused
        body = str(content["body"])
        if body == failing_part and refused < failures:
            refused += 1
            raise ConnectionError("homeserver unavailable")
        room.append(body)
        return f"$event{len(room)}"

    ch._post_message = post  # type: ignore[method-assign]
    return ch, room


async def _send_as_the_bus_does(ch: MatrixChannel) -> str | None:
    msg = OutboundMessage(channel="matrix", recipient_id="!room:test", content="body", user_id="u1")
    with patch("app.channels.providers.matrix.channel.render", return_value=_PARTS):
        return await send_with_retry(
            ch.send,
            msg,
            config=ch.retry_config,
            should_retry=ch.should_retry,
            extract_retry_after=ch.extract_retry_after,
            label="matrix",
        )


@pytest.mark.asyncio
async def test_a_part_that_fails_once_is_retried_alone_and_every_part_reaches_the_room_once() -> None:
    ch, room = _channel(failing_part="part3", failures=1)

    last_id = await _send_as_the_bus_does(ch)

    assert room == _PARTS
    assert last_id == "$event5"


@pytest.mark.asyncio
async def test_a_part_that_keeps_failing_ends_as_a_partial_delivery_without_resending_the_others() -> None:
    ch, room = _channel(failing_part="part3", failures=99)

    with pytest.raises(ChannelSendError) as exc_info:
        await _send_as_the_bus_does(ch)

    assert room == ["part1", "part2"]
    assert exc_info.value.accepted is True
    assert "Delivered 2 of 5" in str(exc_info.value)


@pytest.mark.asyncio
async def test_a_first_part_that_fails_once_is_retried_by_the_bus_and_the_room_gets_it_once() -> None:
    ch, room = _channel(failing_part="part1", failures=1)

    await _send_as_the_bus_does(ch)

    assert room == _PARTS
