"""The port a wake turn asks whether an IM turn holds its chat: one probe at a time, and a probe that fails costs nothing."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from app.services.agent.adaptive_wakeup.chat_busy import is_chat_busy, set_chat_busy_probe


class Probe:
    def __init__(self, *, busy: bool = False, failure: Exception | None = None) -> None:
        self.asked: list[str] = []
        self._busy = busy
        self._failure = failure

    def is_busy(self, chat_id: str) -> bool:
        self.asked.append(chat_id)
        if self._failure is not None:
            raise self._failure
        return self._busy


@pytest.fixture(autouse=True)
def no_probe() -> Iterator[None]:
    set_chat_busy_probe(None)
    yield
    set_chat_busy_probe(None)


def test_without_a_probe_no_chat_is_busy() -> None:
    assert is_chat_busy("chat-1") is False


def test_the_probe_is_asked_about_the_chat_and_its_answer_stands() -> None:
    probe = Probe(busy=True)
    set_chat_busy_probe(probe)

    assert is_chat_busy("chat-1") is True
    assert probe.asked == ["chat-1"]

    set_chat_busy_probe(Probe(busy=False))
    assert is_chat_busy("chat-1") is False


def test_a_replaced_probe_is_the_only_one_asked() -> None:
    old, new = Probe(), Probe()
    set_chat_busy_probe(old)
    set_chat_busy_probe(new)

    is_chat_busy("chat-1")

    assert (old.asked, new.asked) == ([], ["chat-1"])


def test_a_cleared_probe_is_not_asked() -> None:
    probe = Probe(busy=True)
    set_chat_busy_probe(probe)
    set_chat_busy_probe(None)

    assert is_chat_busy("chat-1") is False
    assert probe.asked == []


def test_a_probe_that_fails_counts_as_not_busy_and_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    set_chat_busy_probe(Probe(failure=RuntimeError("router down")))

    with caplog.at_level(logging.WARNING):
        assert is_chat_busy("chat-1") is False

    assert "chat-1" in caplog.text
