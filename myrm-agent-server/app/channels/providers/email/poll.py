"""Email polling: the batch one IMAP poll takes from INBOX, its hand-over to the inbound pipeline, and where the next poll resumes.

[INPUT]
- channels.providers.email.imap::refusal, require_ok, send_imap_id, uidvalidity (POS: IMAP client ID, reply reading, UIDVALIDITY)
- channels.providers.email.inbound::EmailInboundMixin (POS: RFC 822 → InboundMessage parsing)
- channels.types::InboundMessage (POS: inbound message envelope)

[OUTPUT]
- EmailPollMixin: _poll_round, one poll's batch handed to the inbound pipeline; _fetch_new_emails, the batch itself; both used by
  EmailChannel's poll loop

[POS]
Poll half of EmailChannel. The host owns credentials, connections and the loop; the mixin turns one connection into one
batch, hands it to the inbound pipeline, and keeps what the next poll resumes from: the high-water mark, the messages handed
out and not yet confirmed, and the UIDVALIDITY the mark was taken under. Opening INBOX or searching it being refused is an
error carrying the server's words, never read as data, and a message the server refuses to hand over is fetched again by the
next poll instead of being passed over. A poll takes at most 20 messages, oldest first; one the parser cannot read is logged
and skipped. A message that fails for any other reason (a disk error, a connection that drops) ends the poll: the messages
before it are delivered and it is read again by the next poll. A message is confirmed once the pipeline has decided about it,
and until then every poll offers it again, so a stop or reload under a poll does not lose the messages the server has already
marked read; the pipeline failing on one message is logged and does not hold back the others. One poll runs at a time. A
server that numbers INBOX anew is read from its start.
"""

from __future__ import annotations

import asyncio
import imaplib
import logging
import threading
from typing import TYPE_CHECKING

from app.channels.types import InboundMessage

from .imap import refusal, require_ok, send_imap_id, uidvalidity
from .inbound import EmailInboundMixin

logger = logging.getLogger(__name__)

# Messages per poll: a backlog drains over the next polls, oldest first; the first poll has no mark and takes the newest.
_MAX_FETCHED_PER_POLL = 20


class EmailPollMixin(EmailInboundMixin):
    """Email INBOX polling for ``EmailChannel``.

    Requires the host class to provide the attributes below, the connection factory ``_connect_imap`` and the pipeline
    entry ``_emit_inbound``.
    """

    _imap_user: str
    _imap_password: str
    # UIDs above the mark are the ones not yet read; 0 until a message has been, then the poll asks for the unread ones.
    _last_uid: int
    # The UIDVALIDITY the mark was taken under; None until the server has announced one.
    _uidvalidity: bytes | None
    # Messages handed out and not yet confirmed. The thread has moved the mark past them, and while the mark is 0 the
    # server has marked them read, so the unread-message search no longer finds them: only this set offers them again.
    _unconfirmed: set[int]
    # Held by the thread of the poll that is running. Cancelling a poll's delivery does not stop its thread, and a second
    # poll beside it would read the same messages and write the mark back lower.
    _poll_lock: threading.Lock

    if TYPE_CHECKING:

        def _connect_imap(self) -> imaplib.IMAP4_SSL: ...

        async def _emit_inbound(self, msg: InboundMessage) -> None: ...

    async def _poll_round(self) -> None:
        """Read one batch and hand it to the inbound pipeline, confirming each message once the pipeline has decided about it.

        A cancellation (the channel stops or reloads) leaves the message unconfirmed, so the next round offers it again. Any
        other failure of the pipeline on a message is logged and the message is passed over, so one message cannot hold back
        the ones behind it.
        """
        for message in await asyncio.to_thread(self._fetch_new_emails):
            uid = message.metadata.get("uid")
            try:
                await self._emit_inbound(message)
            except Exception:
                logger.warning("Email: the inbound pipeline failed on UID %s; it is skipped", uid, exc_info=True)
            if isinstance(uid, int):
                self._unconfirmed.discard(uid)

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
        """The next batch of messages, or none while the thread of an earlier poll is still running.

        A poll whose delivery was cancelled keeps its thread until it ends; a round that finds one running does nothing and
        the next round carries on.
        """
        if not self._poll_lock.acquire(blocking=False):
            return []
        try:
            return self._read_batch()
        finally:
            self._poll_lock.release()

    def _read_batch(self) -> list[InboundMessage]:
        """Up to ``_MAX_FETCHED_PER_POLL`` of the messages that arrived in INBOX after the high-water mark, oldest first.

        Opening INBOX or searching it being refused raises, and the reconnect loop retries. A refused fetch ends the batch
        instead: the mark stays below that message so the next poll asks for it again, as skipping it would lose it for good.
        A message the parser cannot read is skipped. Any other failure on a message (a disk error saving its attachment, a
        connection that drops) ends the batch the same way, and the messages read before it are still returned; with none
        read yet it raises, and the reconnect loop backs off. The mark moves past a message once it is read or skipped.

        Every UID enters ``_unconfirmed`` before it is fetched and leaves it when the message is skipped, is gone from the
        mailbox, or is confirmed by ``_poll_round``; until then each batch includes it again. A server that announces another
        UIDVALIDITY numbers INBOX anew, so the mark and the unconfirmed UIDs mean nothing any more and the poll starts over
        with the unread messages.
        """
        results: list[InboundMessage] = []
        conn = self._connect_imap()
        mark = self._last_uid
        try:
            conn.login(self._imap_user, self._imap_password)
            send_imap_id(conn)
            require_ok(conn.select("INBOX"), "Opening INBOX")

            if self._renumbered(uidvalidity(conn)):
                logger.warning("Email: the server numbers INBOX anew (UIDVALIDITY changed); reading it from the start")
                mark = 0
                self._unconfirmed.clear()

            criteria = f"(UID {mark + 1}:*)" if mark else "(UNSEEN)"

            msg_nums = require_ok(conn.uid("search", criteria), "Search")
            found = msg_nums[0].split() if msg_nums and msg_nums[0] else []

            # `UID n:*` also answers with the newest message when n is past the end of the mailbox.
            fresh = sorted(uid for uid in map(int, found) if uid > mark)
            batch = fresh[:_MAX_FETCHED_PER_POLL] if mark else fresh[-_MAX_FETCHED_PER_POLL:]
            for uid in sorted({*self._unconfirmed, *batch}):
                self._unconfirmed.add(uid)
                try:
                    status, data = conn.uid("fetch", str(uid), "(RFC822)")
                    if status != "OK":
                        logger.warning("Email: %s; the next poll fetches it again", refusal(f"Fetching UID {uid}", status, data))
                        break
                    if not data or not data[0] or not isinstance(data[0], tuple):
                        self._unconfirmed.discard(uid)
                        continue

                    raw = data[0][1]
                    parsed = self._parse_or_skip(raw, uid) if isinstance(raw, bytes) else None
                    if parsed:
                        results.append(parsed)
                    else:
                        self._unconfirmed.discard(uid)
                    mark = max(mark, uid)
                except Exception:
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
            self._last_uid = mark
            try:
                conn.logout()
            except Exception:
                pass

        return results
