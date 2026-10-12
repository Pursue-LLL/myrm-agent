"""The WhatsApp bridge must not write inbound message content to stderr.

The host logs every bridge stderr line (INFO, or ERROR when the line mentions "error"), so a
console dump of an inbound message ends up in the server log files.
"""

from __future__ import annotations

import re

from app.channels.providers.whatsapp.helpers import _BRIDGE_SCRIPT

_UPSERT_HANDLER = re.compile(r"""sock\.ev\.on\(\s*["']messages\.upsert["']""")
_NEXT_HANDLER = re.compile(r"sock\.ev\.on\(")


def _upsert_handler_source() -> str:
    source = _BRIDGE_SCRIPT.read_text(encoding="utf-8")
    start = _UPSERT_HANDLER.search(source)
    assert start, "messages.upsert handler not found in the bridge script"
    end = _NEXT_HANDLER.search(source, start.end())
    return source[start.start() : end.start() if end else len(source)]


def test_inbound_message_handler_never_writes_to_the_console() -> None:
    offenders = [line.strip() for line in _upsert_handler_source().splitlines() if "console." in line]
    assert offenders == []
