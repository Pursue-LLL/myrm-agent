"""A mailbox that answers the IMAP connection of the mail channel the way a server does, and the failures a poll must survive."""

from __future__ import annotations

import errno
import imaplib
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Literal
from unittest.mock import MagicMock, patch

from app.channels.providers.email import EmailChannel
from app.channels.types import InboundMessage


class Inbox:
    """An IMAP connection to a mailbox holding ``messages`` by UID; ``fetched`` lists every UID asked for.

    It answers as RFC 3501 says a server does: fetching ``RFC822`` marks a message read (§6.4.5), ``(UNSEEN)`` lists only the
    unread ones, ``UID n:*`` answers with the newest message when ``n`` is past the end of the mailbox (§6.4.8), a UID that
    is gone is fetched as ``OK`` with nothing in it, and selecting INBOX announces the UIDVALIDITY (§2.3.1.1) as an
    untagged reply that one read takes away, as ``imaplib`` keeps it. Without a ``uidvalidity`` the server announces none.

    A UID in ``drop_on_fetch`` loses the connection the first time it is fetched: the server has handled the fetch and
    marked the message read, and the reply never arrives. ``on_fetch`` is called with each UID about to be fetched, on the
    thread that fetches it, so a test can hold a poll there.
    """

    def __init__(self, messages: dict[int, bytes], *, descending: bool = False, uidvalidity: int | None = 1) -> None:
        self.messages = dict(messages)
        self.uidvalidity = uidvalidity
        self.seen: set[int] = set()
        self.fetched: list[int] = []
        self.drop_on_fetch: set[int] = set()
        self.on_fetch: Callable[[int], None] | None = None
        self._descending = descending
        self._announcement_pending = False
        self.conn = MagicMock()
        self.conn.select.side_effect = self._select
        self.conn.response.side_effect = self._response
        self.conn.uid.side_effect = self._uid

    def renumber(self, messages: dict[int, bytes], uidvalidity: int) -> None:
        """The server numbers INBOX anew: *messages* are all unread, and the old UIDs mean nothing any more."""
        self.messages = dict(messages)
        self.seen = set()
        self.uidvalidity = uidvalidity

    def poll(self, channel: EmailChannel) -> list[InboundMessage]:
        return poll_and_confirm(channel, self.conn)

    def _select(self, mailbox: str) -> tuple[str, list[object]]:
        self._announcement_pending = self.uidvalidity is not None
        return "OK", [b"1"]

    def _response(self, code: str) -> tuple[str, list[object]]:
        announced = str(self.uidvalidity).encode() if self._announcement_pending else None
        self._announcement_pending = False
        return code, [announced]

    def _uid(self, command: str, *args: str) -> tuple[str, list[object]]:
        if command == "fetch":
            uid = int(args[0])
            self.fetched.append(uid)
            if self.on_fetch:
                self.on_fetch(uid)
            if uid not in self.messages:
                return "OK", [None]
            self.seen.add(uid)
            if uid in self.drop_on_fetch:
                self.drop_on_fetch.discard(uid)
                raise imaplib.IMAP4.abort("socket error: EOF")
            return "OK", [(f"{uid} (RFC822)".encode(), self.messages[uid]), b")"]
        assert command == "search", f"this mailbox does not answer the UID command {command!r}"
        matches = self._matches(args[0])
        return "OK", [b" ".join(str(uid).encode() for uid in (reversed(matches) if self._descending else matches))]

    def _matches(self, criteria: str) -> list[int]:
        """The UIDs a search answers with; a range that starts past the newest message reads as ``newest:start``."""
        uids = sorted(self.messages)
        if criteria == "(UNSEEN)":
            return [uid for uid in uids if uid not in self.seen]
        found = re.fullmatch(r"\(UID (\d+):\*\)", criteria)
        if not found:
            raise AssertionError(f"this mailbox does not answer the search {criteria!r}")
        if not uids:
            return []
        first, last = sorted((int(found.group(1)), uids[-1]))
        return [uid for uid in uids if first <= uid <= last]


def uids(messages: list[InboundMessage]) -> list[int]:
    return [int(str(message.metadata["uid"])) for message in messages]


def poll_and_confirm(channel: EmailChannel, conn: MagicMock) -> list[InboundMessage]:
    """One poll over *conn* whose messages the inbound pipeline takes at once: they are confirmed, so the next poll leaves them be."""
    with patch("imaplib.IMAP4_SSL", return_value=conn):
        messages = channel._fetch_new_emails()
    channel._unconfirmed.difference_update(uids(messages))
    return messages


@contextmanager
def failing_once(kind: Literal["disk", "connection"], uid: int, inbox: Inbox, channel: EmailChannel) -> Iterator[None]:
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
