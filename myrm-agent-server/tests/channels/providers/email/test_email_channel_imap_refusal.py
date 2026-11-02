"""A command the mail server refuses ends the poll with the server's reason or leaves the message for the next poll.

``imaplib`` raises only for a BAD reply; a NO comes back as a status next to the text of the refusal. The channel reads
the status of every command that decides what is fetched, and never moves its high-water mark past a message the server
refused to hand over, so a refusal is neither read as data nor a mail that is lost without a trace.
"""

from __future__ import annotations

import imaplib
import logging
from unittest.mock import MagicMock

import pytest

from app.channels.providers.email import EmailChannel
from app.channels.types import InboundMessage
from tests.channels.providers.email.email_channel_factory import make_channel, raw_mail
from tests.channels.providers.email.email_inbox import poll_and_confirm

_REFUSAL = b"[SERVERBUG] Internal error"
_LOGGER = "app.channels.providers.email.poll"


class _Mailbox:
    """The IMAP connection the channel opens: INBOX holds the UIDs 5 and 6, and every command named in ``refused``
    (``select``, ``search`` or a UID to fetch) is answered with a NO that carries ``reason``."""

    def __init__(self, *, refused: set[str], reason: bytes | None = _REFUSAL) -> None:
        self.refused = refused
        self._reason = reason
        self.fetched: list[str] = []
        self.conn = MagicMock()
        self.conn.select.side_effect = self._select
        self.conn.uid.side_effect = self._uid

    def _answer(self, command: str, ok: list[object]) -> tuple[str, list[object]]:
        return ("NO", [self._reason]) if command in self.refused else ("OK", ok)

    def _select(self, mailbox: str) -> tuple[str, list[object]]:
        return self._answer("select", [b"2"])

    def _uid(self, command: str, *args: str) -> tuple[str, list[object]]:
        if command == "search":
            return self._answer("search", [b"5 6"])
        uid = args[0]
        self.fetched.append(uid)
        return self._answer(uid, [(f"{uid} (RFC822)".encode(), raw_mail(int(uid))), b")"])

    def poll(self, channel: EmailChannel) -> list[InboundMessage]:
        return poll_and_confirm(channel, self.conn)


class TestRefusalBeforeAnythingIsFetched:
    @pytest.mark.parametrize(("refused", "action"), [("select", "Opening INBOX"), ("search", "Search")])
    def test_the_poll_fails_with_the_servers_words(self, refused: str, action: str) -> None:
        mailbox = _Mailbox(refused={refused})

        with pytest.raises(imaplib.IMAP4.error) as raised:
            mailbox.poll(make_channel())

        assert str(raised.value) == f"{action} was refused by the server: {_REFUSAL.decode()}"
        assert mailbox.fetched == []
        mailbox.conn.logout.assert_called_once_with()

    @pytest.mark.parametrize("reason", [None, b"", b"   "], ids=["none", "empty", "blank"])
    def test_a_refusal_without_text_names_the_status(self, reason: bytes | None) -> None:
        """``imaplib`` hands a NO that carries no text over as ``b''``; ``None`` and blanks are defensive shapes."""
        mailbox = _Mailbox(refused={"search"}, reason=reason)

        with pytest.raises(imaplib.IMAP4.error, match="Search was refused by the server: NO$"):
            mailbox.poll(make_channel())


class TestRefusedFetch:
    def test_a_refused_first_message_stops_the_poll_and_moves_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        mailbox = _Mailbox(refused={"5"})
        channel = make_channel()

        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            results = mailbox.poll(channel)

        assert results == []
        assert channel._last_uid == 0
        assert mailbox.fetched == ["5"]
        assert f"Fetching UID 5 was refused by the server: {_REFUSAL.decode()}" in caplog.text
        mailbox.conn.logout.assert_called_once_with()

    def test_the_messages_before_a_refused_one_are_delivered_and_the_refused_one_is_fetched_again(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        mailbox = _Mailbox(refused={"6"})
        channel = make_channel()

        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            first_poll = mailbox.poll(channel)

        assert len(first_poll) == 1
        assert "Body 5" in first_poll[0].content
        assert channel._last_uid == 5
        assert f"Fetching UID 6 was refused by the server: {_REFUSAL.decode()}" in caplog.text

        mailbox.refused.clear()
        second_poll = mailbox.poll(channel)

        assert len(second_poll) == 1
        assert "Body 6" in second_poll[0].content
        assert channel._last_uid == 6
