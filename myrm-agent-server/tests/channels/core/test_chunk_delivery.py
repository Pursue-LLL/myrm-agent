"""``deliver_chunks``: the first chunk is the bus's to retry, every later one is retried alone and never re-sent."""

from __future__ import annotations

import pytest

from app.channels.core.chunk_delivery import deliver_chunks
from app.channels.core.exceptions import ChannelSendError
from app.channels.reliability.retry import RetryConfig, default_extract_retry_after, default_should_retry, send_with_retry
from app.channels.types import OutboundMessage

_NO_WAIT = RetryConfig(max_retries=3, base_delay=0.0, max_delay=0.0, jitter=0.0)


class _Channel:
    name = "fake"
    retry_config = _NO_WAIT

    def should_retry(self, exc: BaseException) -> bool:
        return default_should_retry(exc)

    def extract_retry_after(self, exc: BaseException) -> float | None:
        return default_extract_retry_after(exc)


class _Platform:
    """A platform that takes chunks; ``failures`` maps a chunk index to the errors it raises before it succeeds."""

    def __init__(self, failures: dict[int, list[Exception]] | None = None) -> None:
        self.failures = failures or {}
        self.attempts: list[int] = []
        self.received: list[str] = []

    async def send_chunk(self, chunk: str, index: int) -> str | None:
        self.attempts.append(index)
        pending = self.failures.get(index)
        if pending:
            raise pending.pop(0)
        self.received.append(chunk)
        return f"id-{index}"


def _transient() -> ChannelSendError:
    return ChannelSendError("HTTP 503", channel="fake", status_code=503, retriable=True)


def _rejected() -> ChannelSendError:
    return ChannelSendError("HTTP 400", channel="fake", status_code=400, retriable=False)


class TestDeliverChunks:
    @pytest.mark.asyncio
    async def test_every_chunk_is_sent_once_in_order_and_the_last_id_is_returned(self) -> None:
        platform = _Platform()

        last_id = await deliver_chunks(_Channel(), ["a", "b", "c"], platform.send_chunk)

        assert platform.received == ["a", "b", "c"]
        assert platform.attempts == [0, 1, 2]
        assert last_id == "id-2"

    @pytest.mark.asyncio
    async def test_a_chunk_that_reports_no_id_keeps_the_previous_one(self) -> None:
        async def send_chunk(chunk: str, index: int) -> str | None:
            return "first" if index == 0 else None

        assert await deliver_chunks(_Channel(), ["a", "b"], send_chunk) == "first"

    @pytest.mark.asyncio
    async def test_no_chunks_send_nothing(self) -> None:
        platform = _Platform()

        assert await deliver_chunks(_Channel(), [], platform.send_chunk) is None
        assert platform.attempts == []

    @pytest.mark.asyncio
    async def test_the_first_chunk_failing_is_raised_as_it_is_and_tried_once(self) -> None:
        error = _transient()
        platform = _Platform({0: [error, _transient(), _transient()]})

        with pytest.raises(ChannelSendError) as caught:
            await deliver_chunks(_Channel(), ["a", "b"], platform.send_chunk)

        assert caught.value is error
        assert platform.attempts == [0]

    @pytest.mark.asyncio
    async def test_a_later_chunk_failing_transiently_is_retried_alone(self) -> None:
        platform = _Platform({2: [_transient(), _transient()]})

        last_id = await deliver_chunks(_Channel(), ["a", "b", "c", "d"], platform.send_chunk)

        assert platform.attempts == [0, 1, 2, 2, 2, 3]
        assert platform.received == ["a", "b", "c", "d"]
        assert last_id == "id-3"

    @pytest.mark.asyncio
    async def test_a_later_chunk_failing_past_its_retries_is_a_partial_delivery(self) -> None:
        platform = _Platform({2: [_transient() for _ in range(3)]})

        with pytest.raises(ChannelSendError) as caught:
            await deliver_chunks(_Channel(), ["a", "b", "c", "d"], platform.send_chunk)

        error = caught.value
        assert error.accepted is True
        assert error.retriable is False
        assert error.failed_attachments == ()
        assert error.status_code == 503
        assert "Delivered 2 of 4" in str(error)
        assert isinstance(error.__cause__, ChannelSendError)
        assert platform.attempts == [0, 1, 2, 2, 2]
        assert platform.received == ["a", "b"]

    @pytest.mark.asyncio
    async def test_a_later_chunk_the_platform_rejects_is_not_retried(self) -> None:
        platform = _Platform({1: [_rejected()]})

        with pytest.raises(ChannelSendError) as caught:
            await deliver_chunks(_Channel(), ["a", "b", "c"], platform.send_chunk)

        assert caught.value.accepted is True
        assert platform.attempts == [0, 1]

    @pytest.mark.asyncio
    async def test_an_error_the_channel_does_not_classify_is_still_a_partial_delivery(self) -> None:
        platform = _Platform({1: [ValueError("bad payload")]})

        with pytest.raises(ChannelSendError) as caught:
            await deliver_chunks(_Channel(), ["a", "b"], platform.send_chunk)

        assert caught.value.accepted is True
        assert isinstance(caught.value.__cause__, ValueError)
        assert caught.value.status_code == 0


class TestBusReplay:
    """The bus retries a failed ``send()`` as a whole; a chunk the recipient holds must not go out again."""

    @staticmethod
    async def _send_through_bus(platform: _Platform) -> str | None:
        channel = _Channel()
        message = OutboundMessage(channel="fake", recipient_id="r", user_id="u", content="x")

        async def send(msg: OutboundMessage) -> str | None:
            return await deliver_chunks(channel, ["a", "b", "c", "d", "e"], platform.send_chunk)

        return await send_with_retry(
            send,
            message,
            config=channel.retry_config,
            should_retry=channel.should_retry,
            extract_retry_after=channel.extract_retry_after,
            label="fake",
        )

    @pytest.mark.asyncio
    async def test_a_chunk_failing_for_good_does_not_replay_the_delivered_ones(self) -> None:
        platform = _Platform({2: [_transient() for _ in range(9)]})

        with pytest.raises(ChannelSendError) as caught:
            await self._send_through_bus(platform)

        assert caught.value.accepted is True
        assert platform.received == ["a", "b"]

    @pytest.mark.asyncio
    async def test_a_first_chunk_failing_is_replayed_by_the_bus_and_arrives_once(self) -> None:
        platform = _Platform({0: [_transient(), _transient()]})

        await self._send_through_bus(platform)

        assert platform.received == ["a", "b", "c", "d", "e"]


@pytest.mark.asyncio
async def test_a_later_chunk_waits_as_long_as_the_channel_says_the_platform_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    class PlatformAsksForAWait(_Channel):
        retry_config = RetryConfig(max_retries=3, base_delay=0.0, max_delay=5.0, jitter=0.0)

        def extract_retry_after(self, exc: BaseException) -> float | None:
            return 0.25

    waits: list[float] = []

    async def record_wait(delay: float) -> None:
        waits.append(delay)

    monkeypatch.setattr("app.channels.reliability.retry.asyncio.sleep", record_wait)
    platform = _Platform({1: [_transient()]})

    await deliver_chunks(PlatformAsksForAWait(), ["a", "b"], platform.send_chunk)

    assert waits == [0.25]
