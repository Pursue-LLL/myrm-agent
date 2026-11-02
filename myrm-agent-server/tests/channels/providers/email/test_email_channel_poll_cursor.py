"""Where a poll resumes: a message that failed is read again before any message has moved the mark, and a mailbox the
server numbers anew is read from its start.

Until a message has been delivered the mark is 0 and a poll asks for the unread messages, but the server marks a message
it hands over read, so a message that failed would be lost to that search. A UID means something only under the
UIDVALIDITY the server announced with it (RFC 3501 §2.3.1.1): when the value changes, the mark points at nothing.
"""

from __future__ import annotations

import errno
import imaplib
import logging
from typing import Literal
from unittest.mock import patch

import pytest

from app.channels.providers.email.imap import uidvalidity
from app.channels.types import InboundMessage
from tests.channels.providers.email.email_channel_factory import make_channel, raw_mail
from tests.channels.providers.email.email_inbox import Inbox, failing_once, uids

_LOGGER = "app.channels.providers.email.poll"
_BATCH = (5, 6, 7)


class TestFailureBeforeTheMarkHasMoved:
    def test_a_failure_that_keeps_happening_is_read_again_by_every_poll_until_it_clears(self) -> None:
        inbox = Inbox({uid: raw_mail(uid) for uid in _BATCH})
        channel = make_channel()
        parse = channel._parse_email
        disk_full = True

        def parse_when_the_disk_has_room(raw: bytes, uid: int) -> InboundMessage | None:
            if disk_full and uid == 5:
                raise OSError(errno.ENOSPC, "No space left on device")
            return parse(raw, uid)

        with patch.object(channel, "_parse_email", side_effect=parse_when_the_disk_has_room):
            for _ in range(3):
                with pytest.raises(OSError, match="No space left"):
                    inbox.poll(channel)
            disk_full = False
            recovered = uids(inbox.poll(channel))

        assert recovered == list(_BATCH)
        assert inbox.fetched == [5, 5, 5, 5, 6, 7]
        assert channel._last_uid == 7

    @pytest.mark.parametrize("kind", ["disk", "connection"])
    def test_the_only_message_of_the_mailbox_is_read_again_although_no_unread_one_is_left(
        self, kind: Literal["disk", "connection"]
    ) -> None:
        inbox = Inbox({5: raw_mail(5)})
        channel = make_channel()

        with failing_once(kind, 5, inbox, channel):
            with pytest.raises((OSError, imaplib.IMAP4.abort)):
                inbox.poll(channel)
            retry = uids(inbox.poll(channel))

        assert retry == [5]
        assert inbox.fetched == [5, 5]

    def test_a_message_deleted_in_between_is_no_longer_asked_for(self) -> None:
        inbox = Inbox({uid: raw_mail(uid) for uid in _BATCH})
        channel = make_channel()

        with failing_once("disk", 5, inbox, channel):
            with pytest.raises(OSError, match="No space left"):
                inbox.poll(channel)
            del inbox.messages[5]
            second_poll = uids(inbox.poll(channel))
            third_poll = inbox.poll(channel)

        assert second_poll == [6, 7]
        assert third_poll == []
        assert inbox.fetched == [5, 5, 6, 7]


class TestMailboxNumberedAnew:
    def test_it_is_read_from_its_start_and_the_change_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        inbox = Inbox({uid: raw_mail(uid) for uid in (100, 101, 102)}, uidvalidity=1)
        channel = make_channel()
        first_poll = uids(inbox.poll(channel))

        inbox.renumber({uid: raw_mail(uid) for uid in (1, 2, 3)}, uidvalidity=2)
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            second_poll = uids(inbox.poll(channel))
            third_poll = inbox.poll(channel)

        assert first_poll == [100, 101, 102]
        assert second_poll == [1, 2, 3]
        assert third_poll == []
        assert channel._last_uid == 3
        [warning] = [record for record in caplog.records if record.name == _LOGGER]
        assert "UIDVALIDITY changed" in warning.getMessage()

    def test_the_messages_to_be_read_again_under_the_old_numbering_are_dropped(self) -> None:
        """UID 5 of the old numbering failed; under the new one UID 5 is another message, and a read one."""
        inbox = Inbox({uid: raw_mail(uid) for uid in _BATCH}, uidvalidity=1)
        channel = make_channel()

        with failing_once("disk", 5, inbox, channel):
            with pytest.raises(OSError, match="No space left"):
                inbox.poll(channel)
            inbox.renumber({uid: raw_mail(uid) for uid in range(1, 6)}, uidvalidity=2)
            inbox.seen.add(5)
            poll = uids(inbox.poll(channel))

        assert poll == [1, 2, 3, 4]
        assert inbox.fetched == [5, 1, 2, 3, 4]

    @pytest.mark.parametrize("announced", [1, None], ids=["unchanged", "none"])
    def test_a_value_that_did_not_change_or_never_came_leaves_the_mark_alone(self, announced: int | None) -> None:
        """Starting over would read the older unread messages the first poll left, which the mark has moved past."""
        inbox = Inbox({uid: raw_mail(uid) for uid in range(1, 31)}, uidvalidity=announced)
        channel = make_channel()

        first_poll = uids(inbox.poll(channel))
        second_poll = inbox.poll(channel)

        assert first_poll == list(range(11, 31))
        assert second_poll == []
        assert inbox.fetched == list(range(11, 31))

    def test_a_server_that_stops_announcing_the_value_does_not_restart_the_poll(self) -> None:
        inbox = Inbox({uid: raw_mail(uid) for uid in range(1, 31)})
        channel = make_channel()
        first_poll = uids(inbox.poll(channel))

        inbox.uidvalidity = None
        second_poll = inbox.poll(channel)

        assert first_poll == list(range(11, 31))
        assert second_poll == []
        assert inbox.fetched == list(range(11, 31))


class TestUidValidityReply:
    """``imaplib`` keeps the value as an untagged reply that one read takes away: the second read finds nothing."""

    @staticmethod
    def _connection(replies: dict[str, list[bytes | tuple[bytes, bytes]]]) -> imaplib.IMAP4:
        connection = imaplib.IMAP4.__new__(imaplib.IMAP4)
        connection.debug = 0
        connection.untagged_responses = replies
        return connection

    def test_the_value_is_returned_as_bytes_once(self) -> None:
        connection = self._connection({"UIDVALIDITY": [b"3857529045"]})

        assert uidvalidity(connection) == b"3857529045"
        assert uidvalidity(connection) is None

    def test_a_server_that_announced_none_gives_none(self) -> None:
        assert uidvalidity(self._connection({})) is None

    def test_a_reply_that_is_not_a_plain_value_gives_none(self) -> None:
        """``imaplib`` types a reply as bytes or as a literal pair; only the plain value is a UIDVALIDITY."""
        assert uidvalidity(self._connection({"UIDVALIDITY": [(b"3857529045", b"")]})) is None
