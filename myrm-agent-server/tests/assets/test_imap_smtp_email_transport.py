"""The imap-smtp-email skill script turns a missing setting or a connection that cannot be made into a JSON error.

Reaching a mail server fails in ways a loopback server cannot stage on demand: a setting the skill run did not inject, a
host that refuses or never answers, a server that does not know the ID command, a send the server refuses or breaks
off after the login. ``mail_client.transport`` is imported in process, with ``autospec`` doubles of the stdlib clients standing in
for the sockets, and each failure has to end as ``{"error": ...}`` with exit code 1 rather than a stack trace.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: mail_client.transport imported in process
- tests/assets/conftest.py: the script import path

[OUTPUT]
- Fails when a missing IMAP setting, a refused or timed-out IMAP connection, an SMTP server that cannot be reached, or a
  send it refuses or breaks off is not a JSON error with the reason, or when a server that rejects the ID command stops
  the login from completing

[POS]
In-process transport test of the prebuilt skill script, next to ``test_imap_smtp_email_script.py``, which covers the
certificate checks and the bounds of the same connections through a real handshake.
"""

from __future__ import annotations

import imaplib
import importlib
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from types import ModuleType
from unittest.mock import patch

import pytest

_SETTINGS = {
    "EMAIL_IMAP_HOST": "imap.example.test",
    "EMAIL_IMAP_USER": "agent@example.test",
    "EMAIL_IMAP_PASSWORD": "secret",
}


@pytest.fixture
def transport(skill_modules: None, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for name, value in _SETTINGS.items():
        monkeypatch.setenv(name, value)
    return importlib.import_module("mail_client.transport")


def _error_of(capsys: pytest.CaptureFixture[str], exit_info: pytest.ExceptionInfo[SystemExit]) -> str:
    assert exit_info.value.code == 1
    return str(json.loads(capsys.readouterr().out)["error"])


@pytest.mark.parametrize("name", _SETTINGS)
def test_a_missing_imap_setting_is_a_json_error_naming_it(
    transport: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    monkeypatch.delenv(name)

    with pytest.raises(SystemExit) as exit_info:
        transport.connect_imap()

    assert _error_of(capsys, exit_info) == f"Environment variable {name} is not set"


@pytest.mark.parametrize(
    "failure",
    [ConnectionRefusedError("[Errno 61] Connection refused"), TimeoutError("timed out")],
    ids=["refused", "timed-out"],
)
def test_an_imap_server_that_cannot_be_reached_is_a_json_error_with_the_reason(
    transport: ModuleType, capsys: pytest.CaptureFixture[str], failure: OSError
) -> None:
    with patch("imaplib.IMAP4_SSL", autospec=True, side_effect=failure), pytest.raises(SystemExit) as exit_info:
        transport.connect_imap()

    assert _error_of(capsys, exit_info) == f"IMAP connection failed: {failure}"


def test_a_server_that_rejects_the_id_command_still_completes_the_login(transport: ModuleType) -> None:
    with patch("imaplib.IMAP4_SSL", autospec=True) as imap:
        imap.return_value.xatom.side_effect = imaplib.IMAP4.error("BAD command not recognized")

        conn = transport.connect_imap()

    assert conn is imap.return_value
    conn.login.assert_called_once_with("agent@example.test", "secret")
    assert conn.xatom.call_args.args[0] == "ID"


@pytest.mark.parametrize(
    "failure",
    [
        smtplib.SMTPRecipientsRefused({"bob@example.test": (550, b"no such user")}),
        smtplib.SMTPServerDisconnected("Connection unexpectedly closed"),
        ConnectionResetError("[Errno 54] Connection reset by peer"),
    ],
    ids=["recipient-refused", "disconnected", "reset"],
)
def test_a_send_that_the_smtp_server_refuses_or_breaks_off_is_a_json_error_with_the_reason(
    transport: ModuleType, capsys: pytest.CaptureFixture[str], failure: Exception
) -> None:
    with patch("smtplib.SMTP", autospec=True) as smtp, pytest.raises(SystemExit) as exit_info:
        smtp.return_value.__enter__.return_value.send_message.side_effect = failure
        transport.deliver(MIMEMultipart(), "smtp.example.test", 587, "agent@example.test", "secret")

    assert _error_of(capsys, exit_info) == f"SMTP send failed: {failure}"


def test_an_smtp_server_that_cannot_be_reached_is_a_json_error_with_the_reason(
    transport: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    failure = ConnectionRefusedError("[Errno 61] Connection refused")

    with patch("smtplib.SMTP", autospec=True, side_effect=failure), pytest.raises(SystemExit) as exit_info:
        transport.deliver(MIMEMultipart(), "smtp.example.test", 587, "agent@example.test", "secret")

    assert _error_of(capsys, exit_info) == f"SMTP send failed: {failure}"
