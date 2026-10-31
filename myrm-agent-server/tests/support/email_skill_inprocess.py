"""In-process stand-ins for running the imap-smtp-email skill script's ``main`` without a mail server.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: email_manager.py, imported by the caller through the ``email_manager`` fixture

[OUTPUT]
- imap_client: ``autospec`` double of the connected IMAP client, its folder selection answering a given result
- conn_serving: that double with a UID FETCH that returns one stored message
- run_main: run the script's ``main`` in process against such a double

[POS]
Server pytest-only helper shared by the in-process tests of the skill script (``test_imap_smtp_email_failures.py``,
``test_imap_smtp_email_attachments.py``). The subprocess tests use ``email_skill_script.py`` and a real socket instead.
"""

from __future__ import annotations

import imaplib
import sys
from types import ModuleType
from unittest.mock import MagicMock, create_autospec

import pytest


def imap_client(select_result: tuple[str, list[bytes | None]] = ("OK", [b"0"])) -> MagicMock:
    """A stand-in for the connected IMAP client whose folder selection answers *select_result*."""
    conn: MagicMock = create_autospec(imaplib.IMAP4_SSL, instance=True)
    conn.select.return_value = select_result
    return conn


def conn_serving(raw: bytes) -> MagicMock:
    """An IMAP client whose UID FETCH returns the stored message *raw*."""
    conn = imap_client()
    conn.uid.return_value = ("OK", [(b"1 (RFC822)", raw), b")"])
    return conn


def run_main(email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, conn: MagicMock, *argv: str) -> None:
    """Run the script's ``main`` in process against *conn* in place of a connected IMAP client."""
    monkeypatch.setattr(email_manager, "connect_imap", lambda: conn)
    monkeypatch.setattr(sys, "argv", ["email_manager.py", *argv])
    email_manager.main()
