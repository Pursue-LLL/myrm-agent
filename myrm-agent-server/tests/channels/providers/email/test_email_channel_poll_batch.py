"""What one poll takes from the mailbox: a message nobody can parse never stalls it, a failure on one message delivers the
ones before it and reads it again, and a backlog drains oldest first.

The inbox answers ``UID SEARCH`` the way an IMAP server does, including ``UID n:*`` returning the newest message when
``n`` is past the end of the mailbox, so the batch the channel picks is checked against what a server really sends.
"""

from __future__ import annotations

import errno
import imaplib
import logging
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest

from app.channels.providers.email import EmailChannel
from app.channels.types import InboundMessage
from tests.channels.providers.email.email_channel_factory import make_channel, raw_mail, raw_mail_with_attachments

_LOGGER = "app.channels.providers.email.channel"
_BATCH = (5, 6, 7)


class _Inbox:
    """An IMAP connection to a mailbox holding ``messages`` by UID; ``fetched`` lists every UID asked for.

    A UID in ``drop_on_fetch`` loses the connection the first time it is fetched.
    """

    def __init__(self, messages: dict[int, bytes], *, descending: bool = False) -> None:
        self.messages = messages
        self._descending = descending
        self.fetched: list[int] = []
        self.drop_on_fetch: set[int] = set()
        self.conn = MagicMock()
        self.conn.select.return_value = ("OK", [b"1"])
        self.conn.uid.side_effect = self._uid

    def _uid(self, command: str, *args: str) -> tuple[str, list[object]]:
        if command == "fetch":
            uid = int(args[0])
            self.fetched.append(uid)
            if uid in self.drop_on_fetch:
                self.drop_on_fetch.discard(uid)
                raise imaplib.IMAP4.abort("socket error: EOF")
            return "OK", [(f"{uid} (RFC822)".encode(), self.messages[uid]), b")"]
        matches = self._matches(args[0])
        return "OK", [b" ".join(str(uid).encode() for uid in (reversed(matches) if self._descending else matches))]

    def _matches(self, criteria: str) -> list[int]:
        """The UIDs a search answers with; a range that starts past the newest message reads as ``newest:start``."""
        uids = sorted(self.messages)
        found = re.fullmatch(r"\(UID (\d+):\*\)", criteria)
        if not found:
            return uids
        first, last = sorted((int(found.group(1)), uids[-1]))
        return [uid for uid in uids if first <= uid <= last]

    def poll(self, channel: EmailChannel) -> list[InboundMessage]:
        with patch("imaplib.IMAP4_SSL", return_value=self.conn):
            return channel._fetch_new_emails()


def _uids(messages: list[InboundMessage]) -> list[int]:
    return [int(str(message.metadata["uid"])) for message in messages]


@contextmanager
def _failing_once(kind: Literal["disk", "connection"], uid: int, inbox: _Inbox, channel: EmailChannel) -> Iterator[None]:
    """Make *uid* fail the first time it is read: ``disk`` is a full disk while its mail is parsed, ``connection`` a connection
    that drops while it is fetched."""
    if kind == "connection":
        inbox.drop_on_fetch.add(uid)
        yield
        return
    parse = channel._parse_email
    pending = {uid}

    def parse_unless_disk_full(raw: bytes, parsed_uid: int) -> InboundMessage | None:
        if parsed_uid in pending:
            pending.discard(parsed_uid)
            raise OSError(errno.ENOSPC, "No space left on device")
        return parse(raw, parsed_uid)

    with patch.object(channel, "_parse_email", side_effect=parse_unless_disk_full):
        yield


class TestUnparseableMessage:
    @pytest.mark.parametrize(("unreadable", "readable"), [(5, 6), (6, 5)], ids=["oldest", "newest"])
    def test_it_is_skipped_and_logged_by_uid_and_not_fetched_again(
        self, unreadable: int, readable: int, caplog: pytest.LogCaptureFixture
    ) -> None:
        inbox = _Inbox({5: raw_mail(5), 6: raw_mail(6)})
        channel = make_channel()
        parse = channel._parse_email

        def refuse_unreadable(raw: bytes, uid: int) -> InboundMessage | None:
            if uid == unreadable:
                raise LookupError("unknown encoding")
            return parse(raw, uid)

        with (
            patch.object(channel, "_parse_email", side_effect=refuse_unreadable),
            caplog.at_level(logging.WARNING, logger=_LOGGER),
        ):
            first_poll = inbox.poll(channel)
            second_poll = inbox.poll(channel)

        assert _uids(first_poll) == [readable]
        assert channel._last_uid == 6
        assert [record.getMessage() for record in caplog.records] == [
            f"Email: UID {unreadable} could not be parsed and is skipped"
        ]
        assert caplog.records[0].exc_info is not None
        assert second_poll == []
        assert inbox.fetched == [5, 6]


class TestDiskError:
    def test_a_message_the_disk_could_not_take_is_read_again_by_the_next_poll(self) -> None:
        """A full disk clears up, so the message it failed on is retried, unlike one the parser can never read."""
        inbox = _Inbox({5: raw_mail(5), 6: raw_mail(6)})
        channel = make_channel()
        parse = channel._parse_email
        disk_full = True

        def parse_when_the_disk_has_room(raw: bytes, uid: int) -> InboundMessage | None:
            if disk_full and uid == 5:
                raise OSError(errno.ENOSPC, "No space left on device")
            return parse(raw, uid)

        with patch.object(channel, "_parse_email", side_effect=parse_when_the_disk_has_room):
            with pytest.raises(OSError, match="No space left"):
                inbox.poll(channel)
            assert channel._last_uid == 0

            disk_full = False
            retry = inbox.poll(channel)

        assert _uids(retry) == [5, 6]
        assert inbox.fetched == [5, 5, 6]


class TestBacklog:
    def test_a_backlog_drains_oldest_first_and_each_message_is_fetched_once(self) -> None:
        inbox = _Inbox({uid: raw_mail(uid) for uid in range(101, 131)})
        channel = make_channel()
        channel._last_uid = 100

        first_poll = inbox.poll(channel)
        second_poll = inbox.poll(channel)
        third_poll = inbox.poll(channel)

        assert _uids(first_poll) == list(range(101, 121))
        assert _uids(second_poll) == list(range(121, 131))
        assert third_poll == []
        assert inbox.fetched == list(range(101, 131))
        assert channel._last_uid == 130

    def test_a_server_that_lists_the_uids_newest_first_still_drains_oldest_first(self) -> None:
        """RFC 3501 gives the numbers of a SEARCH response no order."""
        inbox = _Inbox({uid: raw_mail(uid) for uid in range(101, 131)}, descending=True)
        channel = make_channel()
        channel._last_uid = 100

        assert _uids(inbox.poll(channel)) == list(range(101, 121))
        assert channel._last_uid == 120

    def test_the_first_poll_takes_the_newest_unseen_messages(self) -> None:
        inbox = _Inbox({uid: raw_mail(uid) for uid in range(1, 31)})
        channel = make_channel()

        first_poll = inbox.poll(channel)

        assert _uids(first_poll) == list(range(11, 31))
        assert channel._last_uid == 30

    def test_nothing_is_fetched_when_the_search_answers_with_the_newest_old_message(self) -> None:
        """``UID 7:*`` on a mailbox that ends at 6 answers with 6; that message was delivered by an earlier poll."""
        inbox = _Inbox({5: raw_mail(5), 6: raw_mail(6)})
        channel = make_channel()
        channel._last_uid = 6

        assert inbox.poll(channel) == []
        assert inbox.fetched == []


class TestFailureMidBatch:
    """Every message of the batch is delivered exactly once, wherever in it a failure strikes and whatever the failure is."""

    @pytest.mark.parametrize("kind", ["disk", "connection"])
    @pytest.mark.parametrize(("failing", "before"), [(6, [5]), (7, [5, 6])], ids=["middle", "last"])
    def test_the_messages_before_it_are_delivered_and_it_is_read_again(
        self, kind: Literal["disk", "connection"], failing: int, before: list[int], caplog: pytest.LogCaptureFixture
    ) -> None:
        inbox = _Inbox({uid: raw_mail(uid) for uid in _BATCH})
        channel = make_channel()

        with _failing_once(kind, failing, inbox, channel), caplog.at_level(logging.WARNING, logger=_LOGGER):
            first_poll = _uids(inbox.poll(channel))
            mark_after_first_poll = channel._last_uid
            second_poll = _uids(inbox.poll(channel))

        assert first_poll == before
        assert mark_after_first_poll == before[-1]
        assert first_poll + second_poll == list(_BATCH)
        assert inbox.fetched == [*before, failing, *(uid for uid in _BATCH if uid >= failing)]
        [warning] = [record for record in caplog.records if record.name == _LOGGER]
        assert f"UID {failing}" in warning.getMessage()
        assert warning.exc_info is not None

    @pytest.mark.parametrize("kind", ["disk", "connection"])
    def test_a_failure_on_the_first_message_raises_for_the_backoff_and_moves_nothing(
        self, kind: Literal["disk", "connection"]
    ) -> None:
        inbox = _Inbox({uid: raw_mail(uid) for uid in _BATCH})
        channel = make_channel()

        with _failing_once(kind, 5, inbox, channel):
            with pytest.raises((OSError, imaplib.IMAP4.abort)):
                inbox.poll(channel)
            assert channel._last_uid == 0
            retry = _uids(inbox.poll(channel))

        assert retry == list(_BATCH)
        assert inbox.fetched == [5, 5, 6, 7]

    @pytest.mark.parametrize("unreadable", _BATCH, ids=["first", "middle", "last"])
    def test_an_unreadable_message_holds_back_none_of_the_ones_around_it(self, unreadable: int) -> None:
        inbox = _Inbox({uid: raw_mail(uid) for uid in _BATCH})
        channel = make_channel()
        parse = channel._parse_email

        def refuse_unreadable(raw: bytes, uid: int) -> InboundMessage | None:
            if uid == unreadable:
                raise ValueError("bad header")
            return parse(raw, uid)

        with patch.object(channel, "_parse_email", side_effect=refuse_unreadable):
            first_poll = inbox.poll(channel)
            second_poll = inbox.poll(channel)

        assert _uids(first_poll) == [uid for uid in _BATCH if uid != unreadable]
        assert channel._last_uid == 7
        assert second_poll == []
        assert inbox.fetched == list(_BATCH)


class TestUnwritableTempDirectory:
    def test_the_messages_before_the_one_that_cannot_be_saved_are_delivered_and_it_is_saved_once_the_disk_recovers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failure is the file system's own: the attachment of UID 6 has no directory to be written into."""
        inbox = _Inbox({5: raw_mail(5), 6: raw_mail_with_attachments(6, "a.pdf", "b.pdf"), 7: raw_mail(7)})
        channel = make_channel()

        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "missing"))
        first_poll = _uids(inbox.poll(channel))
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        second_poll = inbox.poll(channel)

        assert first_poll == [5]
        assert _uids(second_poll) == [6, 7]
        saved = list(second_poll[0].media)
        assert [attachment.filename for attachment in saved] == ["a.pdf", "b.pdf"]
        assert {Path(str(attachment.path)) for attachment in saved} == set(tmp_path.iterdir())
