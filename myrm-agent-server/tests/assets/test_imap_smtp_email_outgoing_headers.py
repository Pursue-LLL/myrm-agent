"""A message sent by the imap-smtp-email skill script carries a Date and a Message-ID that does not name this machine.

A real mail server (GreenMail, run against the script) stored a sent message with no ``Date`` header and a Message-ID
ending in the sender's own host name. RFC 5322 requires the date, and the Message-ID is shown to every recipient.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: email_manager.py imported in process
- tests/assets/conftest.py: the script import path and the settings ``send`` and ``reply`` need
- tests/support/email_skill_inprocess.py: the IMAP double and the in-process ``main``

[OUTPUT]
- Fails when a sent message has no Date or one that is not a time zone aware date, when its Message-ID is not on the
  sender's domain (the ``EMAIL_FROM_ADDRESS`` address, else the login), falls back to this machine's host name when the
  sender names no domain instead of using the SMTP host, or differs from the id the script reports

[POS]
In-process test of the envelope ``send`` and ``reply`` write, next to ``test_imap_smtp_email_reply.py``, which covers
whom a reply goes to and how it threads.
"""

from __future__ import annotations

import email
import email.message
import email.utils
import json
import socket
from types import ModuleType

import pytest

from tests.support.email_skill_inprocess import conn_serving, run_main

_SEND = ["send", "--to", "bob@example.test", "--subject", "s", "--body", "b"]
_REPLY = ["reply", "--uid", "1", "--body", "b"]
_STORED = b"From: eve@example.test\r\nSubject: invoice\r\nMessage-ID: <1@example.test>\r\n\r\nbody\r\n"


def _sent_by(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outgoing_mail: list[bytes],
    argv: list[str],
) -> tuple[dict[str, str], email.message.Message]:
    """Run *argv*; the script's answer and the message it sent."""
    run_main(email_manager, monkeypatch, conn_serving(_STORED), *argv)
    return json.loads(capsys.readouterr().out), email.message_from_bytes(outgoing_mail[0])


@pytest.mark.parametrize("argv", [_SEND, _REPLY], ids=["send", "reply"])
@pytest.mark.parametrize(
    ("from_address", "domain"),
    [
        pytest.param(None, "example.test", id="the-login"),
        pytest.param("Agent <agent@sender.test>", "sender.test", id="a-from-address-with-a-name"),
        pytest.param("noreply", "smtp.example.test", id="no-domain-falls-back-to-the-smtp-host"),
    ],
)
def test_a_sent_message_has_a_date_and_a_message_id_on_the_senders_domain(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outgoing_mail: list[bytes],
    argv: list[str],
    from_address: str | None,
    domain: str,
) -> None:
    if from_address is not None:
        monkeypatch.setenv("EMAIL_FROM_ADDRESS", from_address)

    answer, sent = _sent_by(email_manager, monkeypatch, capsys, outgoing_mail, argv)

    assert email.utils.parsedate_to_datetime(sent["Date"]).tzinfo is not None
    assert sent["Message-ID"] == answer["message_id"]
    assert sent["Message-ID"].endswith(f"@{domain}>")
    assert socket.getfqdn() not in sent["Message-ID"]
