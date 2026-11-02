"""IMAP conversation helpers of EmailChannel: the RFC 2971 client ID, the reading of a server's reply and its UIDVALIDITY.

[INPUT]
- Standard library ``imaplib`` connection and reply values (no project modules)

[OUTPUT]
- send_imap_id: announce the client to a server that requires it after LOGIN
- refusal: the sentence that says what the server refused and why
- require_ok: the data of a reply, or ``imaplib.IMAP4.error`` carrying the server's words when it refused
- uidvalidity: the UIDVALIDITY a server announced when INBOX was selected, or None

[POS]
Protocol helpers the channel's IMAP poller and health check share. ``imaplib`` raises only for BAD and hands a NO back to the
caller as a status; the helpers here keep the caller from reading a refusal as data, and from misreading what ``imaplib``
keeps of the server's announcements.
"""

from __future__ import annotations

import imaplib
from collections.abc import Sequence
from typing import TypeVar

_ReplyData = TypeVar("_ReplyData", bound=Sequence[object])


def send_imap_id(conn: imaplib.IMAP4_SSL) -> None:
    """Send RFC 2971 IMAP ID command. Required by 163/NetEase after LOGIN."""
    try:
        conn.xatom(
            "ID",
            '("name" "myrm-agent" "version" "1" "vendor" "myrm" "support-email" "noreply@myrm.sh")',
        )
    except Exception:
        pass


def refusal(action: str, status: str, data: Sequence[object]) -> str:
    """What the server refused and why: its own words when it gave any (imaplib hands them over as bytes), else the status."""
    words = data[0].decode("utf-8", errors="replace").strip() if data and isinstance(data[0], bytes) else ""
    return f"{action} was refused by the server: {words or status}"


def require_ok(reply: tuple[str, _ReplyData], action: str) -> _ReplyData:
    """The data of an IMAP command's *reply*; any status but OK means the server refused *action*.

    imaplib raises only for BAD and returns a NO to the caller, who would otherwise read the refusal text as data.
    """
    status, data = reply
    if status != "OK":
        raise imaplib.IMAP4.error(refusal(action, status, data))
    return data


def uidvalidity(conn: imaplib.IMAP4) -> bytes | None:
    """The UIDVALIDITY the server announced when INBOX was selected, or None when it announced none.

    ``imaplib`` keeps the announcement as an untagged reply that one read takes away, so read it once, straight after ``select``.
    """
    announced = conn.response("UIDVALIDITY")[1][0]
    return announced if isinstance(announced, bytes) else None
