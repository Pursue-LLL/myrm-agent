"""Email polling: the batch one IMAP poll takes from INBOX, and where the next poll resumes.

[INPUT]
- channels.providers.email.imap::refusal, require_ok, send_imap_id, uidvalidity (POS: IMAP client ID, reply reading, UIDVALIDITY)
- channels.providers.email.inbound::EmailInboundMixin (POS: RFC 822 → InboundMessage parsing)
- channels.types::InboundMessage (POS: inbound message envelope)

[OUTPUT]
- EmailPollMixin: _fetch_new_emails, one poll's batch of new messages, used by EmailChannel's poll loop

[POS]
Poll half of EmailChannel. The host owns credentials, connections and the loop; the mixin turns one connection into one
batch and keeps what the next poll resumes from: the high-water mark, the messages a failed poll must read again, and the
UIDVALIDITY the mark was taken under. Opening INBOX or searching it being refused is an error carrying the server's words,
never read as data, and a message the server refuses to hand over is fetched again by the next poll instead of being passed
over. A poll takes at most 20 messages, oldest first; one the parser cannot read is logged and skipped. A message that fails
for any other reason (a disk error, a connection that drops) ends the poll: the messages before it are delivered and it is
read again by the next poll, even when no message has moved the mark yet and the server has marked it read. A server that
numbers INBOX anew is read from its start.
"""

from __future__ import annotations

import imaplib
import logging
from typing import TYPE_CHECKING

from app.channels.types import InboundMessage

from .imap import refusal, require_ok, send_imap_id, uidvalidity
from .inbound import EmailInboundMixin

logger = logging.getLogger(__name__)

# Messages per poll: a backlog drains over the next polls, oldest first; the first poll has no mark and takes the newest.
_MAX_FETCHED_PER_POLL = 20


class EmailPollMixin(EmailInboundMixin):
    """Email INBOX polling for ``EmailChannel``.

    Requires the host class to provide the attributes below and the connection factory ``_connect_imap``.
    """

    _imap_user: str
    _imap_password: str
    # UIDs above the mark are the ones not yet delivered; 0 until a message has been, then the poll asks for the unread ones.
    _last_uid: int
    # The UIDVALIDITY the mark was taken under; None until the server has announced one.
    _uidvalidity: bytes | None
    # Messages that failed and must be read again: before the mark has moved, the unread-message search no longer finds them.
    _retry: set[int]

    if TYPE_CHECKING:

        def _connect_imap(self) -> imaplib.IMAP4_SSL: ...

    def _renumbered(self, announced: bytes | None) -> bool:
        """Whether the server announced another UIDVALIDITY than the one the mark was taken under; it is remembered."""
        if announced is None:
            return False
        changed = self._uidvalidity not in (None, announced)
        self._uidvalidity = announced
        return changed

    def _parse_or_skip(self, raw: bytes, uid: int) -> InboundMessage | None:
        """The message in *raw*, or None for one the parser cannot read: that is logged and the poll moves past it.

        A disk error says nothing about the message and clears up, so it propagates and the message is read again.
        """
        try:
            return self._parse_email(raw, uid)
        except OSError:
            raise
        except Exception:
            logger.warning("Email: UID %d could not be parsed and is skipped", uid, exc_info=True)
            return None

    def _fetch_new_emails(self) -> list[InboundMessage]:
        """Up to ``_MAX_FETCHED_PER_POLL`` of the messages that arrived in INBOX after the high-water mark, oldest first.

        Opening INBOX or searching it being refused raises, and the reconnect loop retries. A refused fetch ends the batch
        instead: the mark stays below that message so the next poll asks for it again, as skipping it would lose it for good.
        A message the parser cannot read is skipped. Any other failure on a message (a disk error saving its attachment, a
        connection that drops) ends the batch the same way, and the messages read before it are still returned; with none
        read yet it raises, and the reconnect loop backs off. The mark moves past a message once it is delivered or skipped.

        A failed message is also kept in ``_retry`` and fetched with the next batch until it is delivered, skipped or gone:
        while the mark is 0 the poll asks for the unread messages, and the server marks one it handed over read even when the
        reply never arrived. A server that announces another UIDVALIDITY numbers INBOX anew, so the mark and the retries mean
        nothing any more and the poll starts over with the unread messages.
        """
        results: list[InboundMessage] = []
        conn = self._connect_imap()
        high_water = self._last_uid
        try:
            conn.login(self._imap_user, self._imap_password)
            send_imap_id(conn)
            require_ok(conn.select("INBOX"), "Opening INBOX")

            if self._renumbered(uidvalidity(conn)):
                logger.warning("Email: the server numbers INBOX anew (UIDVALIDITY changed); reading it from the start")
                self._last_uid = high_water = 0
                self._retry.clear()

            criteria = f"(UID {self._last_uid + 1}:*)" if self._last_uid else "(UNSEEN)"

            msg_nums = require_ok(conn.uid("search", criteria), "Search")
            found = msg_nums[0].split() if msg_nums and msg_nums[0] else []

            # `UID n:*` also answers with the newest message when n is past the end of the mailbox.
            fresh = sorted(uid for uid in map(int, found) if uid > self._last_uid)
            batch = fresh[:_MAX_FETCHED_PER_POLL] if self._last_uid else fresh[-_MAX_FETCHED_PER_POLL:]
            for uid in sorted({*self._retry, *batch}):
                try:
                    status, data = conn.uid("fetch", str(uid), "(RFC822)")
                    if status != "OK":
                        logger.warning("Email: %s; the next poll fetches it again", refusal(f"Fetching UID {uid}", status, data))
                        break
                    if not data or not data[0] or not isinstance(data[0], tuple):
                        self._retry.discard(uid)
                        continue

                    raw = data[0][1]
                    parsed = self._parse_or_skip(raw, uid) if isinstance(raw, bytes) else None
                    if parsed:
                        results.append(parsed)
                    high_water = max(high_water, uid)
                    self._retry.discard(uid)
                except Exception:
                    self._retry.add(uid)
                    if not results:
                        raise
                    logger.warning(
                        "Email: reading UID %d failed; the messages before it (%d) are delivered and the next poll reads it again",
                        uid,
                        len(results),
                        exc_info=True,
                    )
                    break

        finally:
            self._last_uid = high_water
            try:
                conn.logout()
            except Exception:
                pass

        return results
