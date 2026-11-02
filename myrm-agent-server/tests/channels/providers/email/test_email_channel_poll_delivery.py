"""What reaches the inbound pipeline: a message is offered again until the pipeline has decided about it, and one poll runs
at a time.

The server marks a message read when it hands it over, so a message that was fetched but never delivered (the channel
stopped or reloaded under the poll, the pipeline failed on it) can only be offered again from what the channel itself
recorded as handed out. Stopping cancels the delivery but not the thread that is fetching, which runs on.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable, Iterator
from unittest.mock import patch

import pytest

from app.channels.providers.email import EmailChannel
from app.channels.types import ChannelStatus, InboundMessage
from tests.channels.providers.email.email_channel_factory import make_channel, raw_mail
from tests.channels.providers.email.email_inbox import Inbox, uids

_LOGGER = "app.channels.providers.email.poll"
_WAIT = 5


class Delivery:
    """A channel polling an ``Inbox`` of 5, 6 and 7 whose inbound pipeline records the UIDs it is handed.

    ``pipeline`` runs before a message is recorded, so a test can make the pipeline fail or stall on it.
    """

    def __init__(self) -> None:
        self.inbox = Inbox({uid: raw_mail(uid) for uid in (5, 6, 7)})
        self.channel: EmailChannel = make_channel()
        self.delivered: list[int] = []
        self.pipeline: Callable[[int], Awaitable[None]] | None = None
        self._released = threading.Event()

    async def emit(self, message: InboundMessage) -> None:
        [uid] = uids([message])
        if self.pipeline:
            await self.pipeline(uid)
        self.delivered.append(uid)

    def hold_first_fetch_of(self, uid: int) -> threading.Event:
        """Hold the thread that fetches *uid* until ``release``; the returned event is set once it is held."""
        reached = threading.Event()
        pending = {uid}

        def hold(fetched: int) -> None:
            if fetched in pending:
                pending.discard(fetched)
                reached.set()
                self._released.wait(_WAIT * 2)

        self.inbox.on_fetch = hold
        return reached

    def release(self) -> None:
        self._released.set()

    async def stop_poll_held_at(self, uid: int) -> None:
        """Start a poll, let its thread reach *uid*, then cancel its delivery the way ``stop`` does; the thread stays held."""
        reached = self.hold_first_fetch_of(uid)
        poll = asyncio.create_task(self.channel._poll_round())
        assert await asyncio.to_thread(reached.wait, _WAIT)
        poll.cancel()
        with pytest.raises(asyncio.CancelledError):
            await poll

    async def until_the_thread_ends(self) -> None:
        for _ in range(_WAIT * 100):
            if not self.channel._poll_lock.locked():
                return
            await asyncio.sleep(0.01)
        raise AssertionError("the thread of the stopped poll never ended")


@pytest.fixture
def delivery() -> Iterator[Delivery]:
    delivery = Delivery()
    with (
        patch("imaplib.IMAP4_SSL", return_value=delivery.inbox.conn),
        patch.object(delivery.channel, "_emit_inbound", side_effect=delivery.emit),
    ):
        yield delivery
    delivery.release()


class TestStopDuringTheFetch:
    async def test_the_messages_a_stopped_poll_took_are_delivered_by_the_next_poll(self, delivery: Delivery) -> None:
        await delivery.stop_poll_held_at(6)
        delivery.release()
        await delivery.until_the_thread_ends()

        await delivery.channel._poll_round()
        await delivery.channel._poll_round()

        assert delivery.delivered == [5, 6, 7]
        assert delivery.channel._unconfirmed == set()

    async def test_a_poll_that_starts_while_the_stopped_one_still_runs_does_nothing(self, delivery: Delivery) -> None:
        await delivery.stop_poll_held_at(6)

        await delivery.channel._poll_round()
        during = (list(delivery.delivered), delivery.channel._last_uid)
        delivery.inbox.messages.update({uid: raw_mail(uid) for uid in (8, 9)})
        delivery.release()
        await delivery.until_the_thread_ends()
        after_the_stopped_poll = delivery.channel._last_uid
        await delivery.channel._poll_round()

        assert during == ([], 0)
        assert after_the_stopped_poll == 7
        assert delivery.delivered == [5, 6, 7, 8, 9]
        assert delivery.channel._last_uid == 9


class TestPipelineDecisions:
    async def test_a_message_the_pipeline_fails_on_is_logged_and_skipped_and_the_others_arrive(
        self, delivery: Delivery, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def fail_on_six(uid: int) -> None:
            if uid == 6:
                raise RuntimeError("handler bug")

        delivery.pipeline = fail_on_six

        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            await delivery.channel._poll_round()
            await delivery.channel._poll_round()

        [warning] = [record for record in caplog.records if record.name == _LOGGER]
        assert delivery.delivered == [5, 7]
        assert delivery.inbox.fetched == [5, 6, 7]
        assert "UID 6" in warning.getMessage()
        assert warning.exc_info is not None
        assert delivery.channel._unconfirmed == set()

    async def test_a_stop_while_the_pipeline_takes_a_message_leaves_it_to_the_next_poll(self, delivery: Delivery) -> None:
        taking = asyncio.Event()
        stalls = {6}

        async def stall_on_six_once(uid: int) -> None:
            if uid in stalls:
                stalls.discard(uid)
                taking.set()
                await asyncio.Event().wait()

        delivery.pipeline = stall_on_six_once
        poll = asyncio.create_task(delivery.channel._poll_round())
        await asyncio.wait_for(taking.wait(), _WAIT)
        poll.cancel()
        with pytest.raises(asyncio.CancelledError):
            await poll
        before_the_next_poll = list(delivery.delivered)

        await delivery.channel._poll_round()

        assert before_the_next_poll == [5]
        assert delivery.delivered == [5, 6, 7]


class TestPollLoop:
    async def test_the_loop_delivers_every_round_until_the_channel_stops(self, delivery: Delivery) -> None:
        channel = delivery.channel
        channel._status = ChannelStatus.RUNNING
        channel._poll_interval = 0.01
        loop = asyncio.create_task(channel._poll_once())

        for _ in range(_WAIT * 100):
            if delivery.delivered == [5, 6, 7]:
                break
            await asyncio.sleep(0.01)
        channel._status = ChannelStatus.STOPPED
        await asyncio.wait_for(loop, _WAIT)

        assert delivery.delivered == [5, 6, 7]
