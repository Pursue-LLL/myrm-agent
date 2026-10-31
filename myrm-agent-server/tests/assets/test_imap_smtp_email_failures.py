"""The imap-smtp-email skill script reports a failure after the connection is up as JSON, not as a stack trace.

A loopback server cannot produce these faults on demand (a socket error in the middle of a command, a refusal without
text), and a header value with a line break only fails inside the standard library's own serialization. So the script's
``main`` runs in process, against an ``autospec`` double of the IMAP client.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: email_manager.py imported in process
- tests/assets/conftest.py: the script import path

[OUTPUT]
- Fails when a socket error, a refused folder, a NUL in an argument or a header value with a line break ends as a stack
  trace instead of the JSON error, when a message with clean headers is no longer sent, or when a reply to a sender
  whose name is raw UTF-8 does not go to that sender's address

[POS]
In-process failure-reporting test of the prebuilt skill script, next to ``test_imap_smtp_email_commands.py``, which
covers the commands it sends.
"""

from __future__ import annotations

import imaplib
import importlib
import json
import sys
from types import ModuleType
from unittest.mock import MagicMock, create_autospec

import pytest

_REFUSAL = b"[ALERT] The folder is locked"


@pytest.fixture
def email_manager(skill_modules: None) -> ModuleType:
    return importlib.import_module("email_manager")


def _imap_client(select_result: tuple[str, list[bytes | None]] = ("OK", [b"0"])) -> MagicMock:
    """A stand-in for the connected IMAP client whose folder selection answers *select_result*."""
    conn: MagicMock = create_autospec(imaplib.IMAP4_SSL, instance=True)
    conn.select.return_value = select_result
    return conn


def _run_main(email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, conn: MagicMock, *argv: str) -> None:
    """Run the script's ``main`` in process against *conn* in place of a connected IMAP client."""
    monkeypatch.setattr(email_manager, "connect_imap", lambda: conn)
    monkeypatch.setattr(sys, "argv", ["email_manager.py", *argv])
    email_manager.main()


def _failure_of(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], conn: MagicMock, *argv: str
) -> object:
    with pytest.raises(SystemExit) as exit_info:
        _run_main(email_manager, monkeypatch, conn, *argv)
    assert exit_info.value.code == 1
    return json.loads(capsys.readouterr().out)["error"]


def test_a_socket_failure_after_the_connection_is_up_is_a_json_error(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = _imap_client()
    conn.uid.side_effect = OSError("cannot read from timed out object")

    error = _failure_of(email_manager, monkeypatch, capsys, conn, "check")

    assert error == "Email command 'check' failed: cannot read from timed out object"
    conn.logout.assert_called_once_with()


@pytest.mark.parametrize(
    "argv",
    [["search", "--subject", "x\x00y"], ["check", "--folder", "x\x00y"], ["mark-read", "x\x00y"]],
    ids=["search-text", "folder", "uids"],
)
def test_a_nul_in_an_argument_is_refused_before_any_uid_command(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    """A NUL cannot be passed on a command line, so this is the one line end the subprocess tests cannot send."""
    conn = _imap_client()

    assert _failure_of(email_manager, monkeypatch, capsys, conn, *argv)

    conn.uid.assert_not_called()


@pytest.fixture
def outgoing_mail(email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings for ``send`` and ``reply``, with ``deliver`` reduced to the serialization ``smtplib`` starts with."""
    monkeypatch.setenv("EMAIL_IMAP_HOST", "imap.example.test")
    monkeypatch.setenv("EMAIL_IMAP_USER", "agent@example.test")
    monkeypatch.setenv("EMAIL_IMAP_PASSWORD", "secret")
    monkeypatch.setattr(email_manager, "deliver", lambda msg, *_connection: msg.as_bytes())


def _conn_serving(raw: bytes) -> MagicMock:
    """An IMAP client whose UID FETCH returns the stored message *raw*."""
    conn = _imap_client()
    conn.uid.return_value = ("OK", [(b"1 (RFC822)", raw), b")"])
    return conn


def _conn_holding(subject: str | None) -> MagicMock:
    """An IMAP client whose UID FETCH returns a stored message with *subject*, if there is one."""
    if subject is None:
        return _imap_client()
    return _conn_serving(f"From: eve@example.test\r\nSubject: {subject}\r\nMessage-ID: <1@example.test>\r\n\r\nbody\r\n".encode())


_SEND = ["send", "--to", "bob@example.test", "--subject", "s", "--body", "b"]
_REPLY = ["reply", "--uid", "1", "--body", "b"]
# An RFC 2047 subject that decodes to a line break followed by a header line.
_CRAFTED_SUBJECT = "=?utf-8?q?hi=0D=0ABcc:_evil@x.test?="


@pytest.mark.usefixtures("outgoing_mail")
@pytest.mark.parametrize(
    ("argv", "stored_subject"),
    [
        pytest.param(
            ["send", "--to", "bob@example.test\r\nBcc: evil@x.test", "--subject", "s", "--body", "b"], None, id="recipient"
        ),
        pytest.param(
            ["send", "--to", "bob@example.test", "--subject", "s\r\nBcc: evil@x.test", "--body", "b"], None, id="subject"
        ),
        pytest.param(_REPLY, _CRAFTED_SUBJECT, id="reply-to-a-crafted-subject"),
    ],
)
def test_a_header_with_a_line_break_is_a_json_error_instead_of_a_stack_trace(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    stored_subject: str | None,
) -> None:
    error = _failure_of(email_manager, monkeypatch, capsys, _conn_holding(stored_subject), *argv)

    assert str(error).startswith(f"Email command '{argv[0]}' failed: ")


@pytest.mark.usefixtures("outgoing_mail")
@pytest.mark.parametrize(
    ("argv", "stored_subject"),
    [pytest.param(_SEND, None, id="send"), pytest.param(_REPLY, "invoice", id="reply")],
)
def test_a_message_with_clean_headers_is_sent(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    stored_subject: str | None,
) -> None:
    _run_main(email_manager, monkeypatch, _conn_holding(stored_subject), *argv)

    assert json.loads(capsys.readouterr().out)["status"] == "sent"


@pytest.mark.usefixtures("outgoing_mail")
@pytest.mark.parametrize(
    "sender_headers",
    [
        pytest.param("From: 发票 <a@b.test>\r\n", id="from"),
        pytest.param("From: eve@example.test\r\nReply-To: 发票 <a@b.test>\r\n", id="reply-to"),
    ],
)
def test_a_reply_goes_to_the_address_of_a_sender_whose_name_is_raw_utf_8(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], sender_headers: str
) -> None:
    """Raw UTF-8 in the header makes the parser return a ``Header`` object, which ``parseaddr`` cannot read as an address."""
    raw = f"{sender_headers}Subject: invoice\r\nMessage-ID: <1@example.test>\r\n\r\nbody\r\n".encode()

    _run_main(email_manager, monkeypatch, _conn_serving(raw), *_REPLY)

    assert json.loads(capsys.readouterr().out)["to"] == "a@b.test"


@pytest.mark.parametrize(
    "argv",
    [
        ["check"],
        ["search", "--subject", "x"],
        ["read", "1"],
        ["download", "1"],
        ["reply", "--uid", "1", "--body", "b"],
        ["mark-read", "1"],
        ["mark-unread", "1"],
    ],
    ids=lambda argv: argv[0],
)
def test_every_command_that_opens_a_folder_reports_a_refusal(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    conn = _imap_client(("NO", [_REFUSAL]))

    error = _failure_of(email_manager, monkeypatch, capsys, conn, *argv, "--folder", "Nope")

    assert (
        error
        == f"Mailbox 'Nope' could not be opened: {_REFUSAL.decode()}. Run the `folders` command to list the available folders"
    )
    conn.uid.assert_not_called()


def test_a_refusal_without_text_is_reported_with_the_status(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = _imap_client(("NO", [None]))

    error = _failure_of(email_manager, monkeypatch, capsys, conn, "check", "--folder", "Nope")

    assert str(error).startswith("Mailbox 'Nope' could not be opened: NO. ")
