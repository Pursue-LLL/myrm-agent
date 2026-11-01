"""The imap-smtp-email skill script reports a failure after the connection is up as JSON, not as a stack trace.

A loopback server cannot produce these faults on demand (a socket error in the middle of a command, a refusal without
text), and a header value with a line break, like an attached message the generator cannot write, only fails inside the
standard library's own serialization. So the script's ``main`` runs in process, against an ``autospec`` double of the IMAP
client.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: email_manager.py imported in process
- tests/assets/conftest.py: the script import path

[OUTPUT]
- Fails when a socket error, a refused folder, a NUL in an argument, a header value with a line break or a message that
  is gone or empty ends as a stack trace or an unclear error instead of the JSON error, when a message with clean
  headers is no longer sent, or when an attached message that the generator cannot write (a nesting that exhausts the
  stack, a refusal of the generator) fails ``download`` instead of being left out

[POS]
In-process failure-reporting test of the prebuilt skill script, next to ``test_imap_smtp_email_commands.py``, which
covers the commands it sends.
"""

from __future__ import annotations

import email.errors
import email.message
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from tests.support.email_skill_inprocess import conn_serving, imap_client, run_main

_REFUSAL = b"[ALERT] The folder is locked"


def _failure_of(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], conn: MagicMock, *argv: str
) -> object:
    with pytest.raises(SystemExit) as exit_info:
        run_main(email_manager, monkeypatch, conn, *argv)
    assert exit_info.value.code == 1
    return json.loads(capsys.readouterr().out)["error"]


def test_a_socket_failure_after_the_connection_is_up_is_a_json_error(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = imap_client()
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
    conn = imap_client()

    assert _failure_of(email_manager, monkeypatch, capsys, conn, *argv)

    conn.uid.assert_not_called()


def _conn_holding(subject: str | None) -> MagicMock:
    """An IMAP client whose UID FETCH returns a stored message with *subject*, if there is one."""
    if subject is None:
        return imap_client()
    return conn_serving(f"From: eve@example.test\r\nSubject: {subject}\r\nMessage-ID: <1@example.test>\r\n\r\nbody\r\n".encode())


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
    run_main(email_manager, monkeypatch, _conn_holding(stored_subject), *argv)

    assert json.loads(capsys.readouterr().out)["status"] == "sent"


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
    conn = imap_client(("NO", [_REFUSAL]))

    error = _failure_of(email_manager, monkeypatch, capsys, conn, *argv, "--folder", "Nope")

    assert (
        error
        == f"Mailbox 'Nope' could not be opened: {_REFUSAL.decode()}. Run the `folders` command to list the available folders"
    )
    conn.uid.assert_not_called()


@pytest.mark.parametrize(
    ("stored", "error"),
    [
        pytest.param([], "Message UID 1 not found", id="nothing-stored"),
        pytest.param([None], "Message UID 1 not found", id="no-entry"),
        pytest.param([b")"], "Message UID 1 not found", id="no-literal"),
        pytest.param([(b"1 (RFC822)", None)], "Message UID 1 has no content", id="no-content"),
    ],
)
@pytest.mark.parametrize("argv", [["read", "1"], ["download", "1"], _REPLY], ids=lambda argv: argv[0])
def test_a_message_that_is_gone_or_empty_is_reported_by_every_command_that_reads_it(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    stored: list[object],
    error: str,
) -> None:
    conn = imap_client()
    conn.uid.return_value = ("OK", stored)

    assert _failure_of(email_manager, monkeypatch, capsys, conn, *argv) == error
    conn.logout.assert_called_once_with()


def test_a_refusal_without_text_is_reported_with_the_status(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = imap_client(("NO", [None]))

    error = _failure_of(email_manager, monkeypatch, capsys, conn, "check", "--folder", "Nope")

    assert str(error).startswith("Mailbox 'Nope' could not be opened: NO. ")


_FORWARDED = "From: eve@x.test\r\nSubject: invoice\r\n\r\nhello\r\n"
_NESTED_PAST_THE_STACK = "Content-Type: message/rfc822\r\n\r\n" * (sys.getrecursionlimit() // 2) + _FORWARDED


def _mail_with_an_attached_message(attached: str) -> bytes:
    """A message with a PDF and, as its second attachment, *attached* written into a ``message/rfc822`` part."""
    return (
        "From: a@x.test\r\nMessage-ID: <1@x.test>\r\nMIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary=b\r\n\r\n"
        '--b\r\nContent-Type: application/pdf\r\nContent-Disposition: attachment; filename="a.pdf"\r\n\r\n%PDF-1.4\r\n'
        '--b\r\nContent-Type: message/rfc822\r\nContent-Disposition: attachment; filename="fwd.eml"\r\n\r\n'
        f"{attached}\r\n--b--\r\n"
    ).encode()


def _download_leaving_out_the_attached_message(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, attached: str
) -> None:
    """``read`` lists both files and ``download`` saves the PDF only: the message is left out, not saved cut short."""
    raw = _mail_with_an_attached_message(attached)

    run_main(email_manager, monkeypatch, conn_serving(raw), "read", "1")
    listed = [entry["filename"] for entry in json.loads(capsys.readouterr().out)["attachments"]]
    run_main(email_manager, monkeypatch, conn_serving(raw), "download", "1", "--output-dir", str(tmp_path))
    answer = json.loads(capsys.readouterr().out)

    assert listed == ["a.pdf", "fwd.eml"]
    assert answer["status"] == "downloaded"
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == {"a.pdf": b"%PDF-1.4"}


def test_download_saves_the_rest_when_an_attached_message_is_nested_past_the_stack(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The parser reads such a message, but writing it back takes several frames a level and runs out of stack."""
    _download_leaving_out_the_attached_message(email_manager, monkeypatch, capsys, tmp_path, _NESTED_PAST_THE_STACK)


def test_download_saves_the_rest_when_the_generator_refuses_an_attached_message(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A refusal of the generator, whatever its reason, ends no more than the file of that message."""

    def refuse(*_args: object, **_kwargs: object) -> bytes:
        raise email.errors.HeaderWriteError("folded header contains newline")

    monkeypatch.setattr(email.message.Message, "as_bytes", refuse)

    _download_leaving_out_the_attached_message(email_manager, monkeypatch, capsys, tmp_path, _FORWARDED)
