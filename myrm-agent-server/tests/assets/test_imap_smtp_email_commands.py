"""The imap-smtp-email skill script sends only well-formed IMAP commands and says what it refuses.

Search terms, folder names and UID lists come from the user or the model and end up inside a command line, and imaplib
joins string arguments without quoting or validating them: a line break in any of them would start a second command.
These tests run the script against a loopback IMAP server that records each command line it receives, so every
assertion is on the exact lines that reached the wire.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: email_manager.py run as a subprocess
- tests/support/email_skill_script.py: the loopback listener and the script runner
- tests/assets/conftest.py: the loopback certificate

[OUTPUT]
- Fails when a line break or quote in a search term, folder name or UID list changes the command the server receives,
  when a refused argument is not explained, or when a folder the server refuses or a connection that drops ends as
  anything but a JSON error with the reason

[POS]
Command-safety test of the prebuilt skill script, next to ``test_imap_smtp_email_failures.py``, which covers the
failures only an in-process double can produce, and ``test_imap_smtp_email_script.py``, which covers the handshake.
"""

from __future__ import annotations

import json
import socket
import ssl
import subprocess
from pathlib import Path

import pytest

from tests.support.email_skill_script import run_email_script, serve_sessions

# The connection set-up and tear-down of every run; the commands under test are what comes between.
_HOUSEKEEPING = frozenset({"CAPABILITY", "ID", "LOGIN", "LOGOUT"})
_INJECTED = "Z9 DELETE Archive"
_TEXT = "<text>"  # where a test puts the argument under test in a command line
_REFUSAL = b"[NONEXISTENT] Unknown Mailbox"


class _Mailbox:
    """A logged-in IMAP server with an empty mailbox that records every command line it is sent, tags removed."""

    def __init__(self, *, refuse_folder: bool = False, drop_on_search: bool = False) -> None:
        self.commands: list[str] = []
        self._refuse_folder = refuse_folder
        self._drop_on_search = drop_on_search

    def session(self, conn: socket.socket, context: ssl.SSLContext) -> None:
        with context.wrap_socket(conn, server_side=True) as tls, tls.makefile("rwb") as stream:
            stream.write(b"* OK IMAP4rev1 ready\r\n")
            stream.flush()
            for raw in stream:
                tag, _, command = raw.decode().rstrip("\r\n").partition(" ")
                verb = command.split(" ", 1)[0].upper()
                if verb not in _HOUSEKEEPING:
                    self.commands.append(command)
                if verb == "UID" and self._drop_on_search:
                    return
                stream.write(self._reply(tag, command))
                stream.flush()

    def _reply(self, tag: str, command: str) -> bytes:
        verb, _, rest = command.partition(" ")
        match verb.upper():
            case "CAPABILITY":
                return f"* CAPABILITY IMAP4rev1\r\n{tag} OK done\r\n".encode()
            case "SELECT" | "EXAMINE" if self._refuse_folder:
                return f"{tag} NO {_REFUSAL.decode()}\r\n".encode()
            case "SELECT" | "EXAMINE":
                return f"* 0 EXISTS\r\n{tag} OK [READ-WRITE] done\r\n".encode()
            case "UID" if rest.upper().startswith("SEARCH"):
                return f"* SEARCH\r\n{tag} OK done\r\n".encode()
            case "LOGOUT":
                return f"* BYE\r\n{tag} OK done\r\n".encode()
            case _:
                return f"{tag} OK done\r\n".encode()


def _run_against(
    tmp_path: Path, tls: tuple[ssl.SSLContext, Path], mailbox: _Mailbox, args: list[str]
) -> subprocess.CompletedProcess[str]:
    with serve_sessions(mailbox.session, tls[0]) as port:
        return run_email_script(tmp_path, args, port=port, trust=tls[1])


def _error_of(proc: subprocess.CompletedProcess[str]) -> str:
    assert proc.returncode == 1, proc.stderr
    assert "Traceback" not in proc.stderr
    return str(json.loads(proc.stdout)["error"])


@pytest.mark.parametrize(
    ("args", "commands"),
    [
        pytest.param(["search", "--subject", f"x\r\n{_INJECTED}"], ["EXAMINE INBOX"], id="search-subject"),
        pytest.param(["search", "--from", f"x\r\n{_INJECTED}"], ["EXAMINE INBOX"], id="search-from"),
        pytest.param(["search", "--to", f"x\r\n{_INJECTED}"], ["EXAMINE INBOX"], id="search-to"),
        pytest.param(["search", "--keyword", f"x\r\n{_INJECTED}"], ["EXAMINE INBOX"], id="search-keyword"),
        pytest.param(["search", "--since", f"x\r\n{_INJECTED}"], ["EXAMINE INBOX"], id="search-since"),
        pytest.param(["check", "--folder", f"INBOX\r\n{_INJECTED}"], [], id="folder"),
        pytest.param(["mark-read", f"1\r\n{_INJECTED}"], ["SELECT INBOX"], id="mark-read-uids"),
        pytest.param(["mark-unread", f"1\r\n{_INJECTED}"], ["SELECT INBOX"], id="mark-unread-uids"),
    ],
)
def test_a_line_break_in_an_argument_never_becomes_another_command(
    tmp_path: Path, listener_tls: tuple[ssl.SSLContext, Path], args: list[str], commands: list[str]
) -> None:
    mailbox = _Mailbox()

    proc = _run_against(tmp_path, listener_tls, mailbox, args)

    assert _error_of(proc)
    assert mailbox.commands == commands


@pytest.mark.parametrize("separator", ["\r\n", "\r", "\n"], ids=["crlf", "cr", "lf"])
@pytest.mark.parametrize(
    ("template", "commands"),
    [
        pytest.param(["search", "--subject", _TEXT], ["EXAMINE INBOX"], id="search-text"),
        pytest.param(["check", "--folder", _TEXT], [], id="folder"),
        pytest.param(["mark-read", _TEXT], ["SELECT INBOX"], id="uids"),
    ],
)
def test_every_kind_of_line_end_is_refused_in_each_kind_of_argument(
    tmp_path: Path, listener_tls: tuple[ssl.SSLContext, Path], template: list[str], commands: list[str], separator: str
) -> None:
    mailbox = _Mailbox()
    args = [f"x{separator}y" if arg == _TEXT else arg for arg in template]

    proc = _run_against(tmp_path, listener_tls, mailbox, args)

    assert _error_of(proc)
    assert mailbox.commands == commands


@pytest.mark.parametrize(
    ("args", "commands"),
    [
        pytest.param(["check"], ["EXAMINE INBOX", "UID SEARCH (ALL)"], id="default-folder-unchanged"),
        pytest.param(["check", "--folder", "[Gmail]/Drafts"], ["EXAMINE [Gmail]/Drafts", "UID SEARCH (ALL)"], id="plain-name"),
        pytest.param(["check", "--folder", "&XfJT0ZAB-"], ["EXAMINE &XfJT0ZAB-", "UID SEARCH (ALL)"], id="utf7-folder"),
        pytest.param(["check", "--folder", "Sent Items"], ['EXAMINE "Sent Items"', "UID SEARCH (ALL)"], id="spaced-folder"),
        pytest.param(["search", "--subject", "invoice"], ["EXAMINE INBOX", 'UID SEARCH (SUBJECT "invoice")'], id="plain-term"),
        pytest.param(
            ["search", "--subject", 'say "hi" a\\b'],
            ["EXAMINE INBOX", 'UID SEARCH (SUBJECT "say \\"hi\\" a\\\\b")'],
            id="subject-escaped",
        ),
        pytest.param(["search", "--from", 'a "b"'], ["EXAMINE INBOX", 'UID SEARCH (FROM "a \\"b\\"")'], id="from-escaped"),
        pytest.param(["search", "--to", 'a "b"'], ["EXAMINE INBOX", 'UID SEARCH (TO "a \\"b\\"")'], id="to-escaped"),
        pytest.param(["search", "--keyword", 'a "b"'], ["EXAMINE INBOX", 'UID SEARCH (BODY "a \\"b\\"")'], id="keyword-escaped"),
        pytest.param(["search", "--since", 'a"b'], ["EXAMINE INBOX", 'UID SEARCH (SINCE "a\\"b")'], id="since-escaped"),
        pytest.param(
            ["mark-read", "1,5:9"],
            ["SELECT INBOX", "UID STORE 1 +FLAGS (\\Seen)", "UID STORE 5:9 +FLAGS (\\Seen)"],
            id="uid-and-range",
        ),
    ],
)
def test_arguments_reach_the_server_quoted_and_the_default_commands_are_unchanged(
    tmp_path: Path, listener_tls: tuple[ssl.SSLContext, Path], args: list[str], commands: list[str]
) -> None:
    mailbox = _Mailbox()

    proc = _run_against(tmp_path, listener_tls, mailbox, args)

    assert proc.returncode == 0, proc.stderr
    assert mailbox.commands == commands


@pytest.mark.parametrize(
    ("uids", "message"),
    [
        ("1,abc", "Invalid UID 'abc'"),
        ("1,5:*x", "Invalid UID '5:*x'"),
        ("1,\u0663", "Invalid UID '\u0663'"),
        (" , ", "At least one UID is required"),
    ],
    ids=["word", "range-with-letter", "non-ascii-digit", "empty"],
)
def test_an_invalid_uid_list_is_refused_before_any_uid_is_sent(
    tmp_path: Path, listener_tls: tuple[ssl.SSLContext, Path], uids: str, message: str
) -> None:
    mailbox = _Mailbox()

    proc = _run_against(tmp_path, listener_tls, mailbox, ["mark-read", uids])

    assert _error_of(proc).startswith(message)
    assert mailbox.commands == ["SELECT INBOX"]


def test_a_folder_the_server_refuses_is_reported_with_its_reason(
    tmp_path: Path, listener_tls: tuple[ssl.SSLContext, Path]
) -> None:
    mailbox = _Mailbox(refuse_folder=True)

    proc = _run_against(tmp_path, listener_tls, mailbox, ["check", "--folder", "Sent"])

    error = _error_of(proc)
    assert error.startswith("Mailbox 'Sent' could not be opened: ")
    assert _REFUSAL.decode() in error
    assert "`folders`" in error
    assert mailbox.commands == ["EXAMINE Sent"]


def test_a_connection_dropped_in_the_middle_of_a_command_is_a_json_error(
    tmp_path: Path, listener_tls: tuple[ssl.SSLContext, Path]
) -> None:
    mailbox = _Mailbox(drop_on_search=True)

    proc = _run_against(tmp_path, listener_tls, mailbox, ["search", "--subject", "x"])

    assert _error_of(proc).startswith("Email command 'search' failed: ")


@pytest.mark.parametrize(
    ("args", "commands", "hint"),
    [
        pytest.param(
            ["search", "--subject", "发票"],
            ["EXAMINE INBOX"],
            "This script sends only ASCII search text to the IMAP server; list recent messages with `check` and filter them "
            "by subject or sender yourself",
            id="search-text",
        ),
        pytest.param(
            ["check", "--folder", "已发送"],
            [],
            "Folder '已发送' is not ASCII: use the name exactly as the `folders` command lists it",
            id="folder",
        ),
    ],
)
def test_non_ascii_text_is_explained_instead_of_crashing(
    tmp_path: Path, listener_tls: tuple[ssl.SSLContext, Path], args: list[str], commands: list[str], hint: str
) -> None:
    mailbox = _Mailbox()

    proc = _run_against(tmp_path, listener_tls, mailbox, args)

    assert _error_of(proc) == hint
    assert mailbox.commands == commands
