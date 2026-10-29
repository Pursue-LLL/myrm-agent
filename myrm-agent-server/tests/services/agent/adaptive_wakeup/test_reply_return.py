"""The port a wake turn's reply leaves the app through: one carrier at a time, and a carrier that fails costs nothing."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.services.agent.adaptive_wakeup import reply_return
from app.services.agent.adaptive_wakeup.reply_return import return_wake_reply, set_wake_reply_returner


class Carrier:
    def __init__(self, failure: Exception | None = None) -> None:
        self.carried: list[tuple[str, str]] = []
        self._failure = failure

    async def return_reply(self, chat_id: str, reply: str) -> None:
        if self._failure is not None:
            raise self._failure
        self.carried.append((chat_id, reply))


@pytest.fixture(autouse=True)
def no_carrier() -> Iterator[None]:
    set_wake_reply_returner(None)
    yield
    set_wake_reply_returner(None)


@pytest.mark.asyncio
async def test_without_a_carrier_the_reply_goes_nowhere() -> None:
    await return_wake_reply("chat-1", "done")


@pytest.mark.asyncio
async def test_the_carrier_gets_the_chat_and_the_reply() -> None:
    carrier = Carrier()
    set_wake_reply_returner(carrier)

    await return_wake_reply("chat-1", "done")

    assert carrier.carried == [("chat-1", "done")]


@pytest.mark.asyncio
async def test_a_replaced_carrier_is_the_only_one_asked() -> None:
    old, new = Carrier(), Carrier()
    set_wake_reply_returner(old)
    set_wake_reply_returner(new)

    await return_wake_reply("chat-1", "done")

    assert (old.carried, new.carried) == ([], [("chat-1", "done")])


@pytest.mark.asyncio
async def test_a_carrier_that_fails_is_logged_and_does_not_end_the_wake_turn(caplog: pytest.LogCaptureFixture) -> None:
    set_wake_reply_returner(Carrier(RuntimeError("channel down")))

    with caplog.at_level("WARNING", logger=reply_return.logger.name):
        await return_wake_reply("chat-1", "done")

    assert "could not be returned: session=chat-1" in caplog.text
