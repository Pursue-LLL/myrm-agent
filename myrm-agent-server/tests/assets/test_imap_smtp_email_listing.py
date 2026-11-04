"""The imap-smtp-email skill script lists, searches and filters messages as its documentation says.

``check`` and ``search`` print a JSON summary of the headers they find, ``--unread-only`` and ``--since`` become IMAP
search criteria (``--since`` takes an age such as 7d, 24h or 2w and turns it into a date), and ``folders`` prints the
mailbox names. The script's ``main`` runs in process against an ``autospec`` double of the IMAP client, so each test sees
both the criterion that was sent and the JSON that was printed; the exact command lines are in
``test_imap_smtp_email_commands.py``.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: email_manager.py imported in process
- tests/assets/conftest.py: the script import path
- tests/support/email_skill_inprocess.py: the IMAP client double and the ``main`` runner

[OUTPUT]
- Fails when a listing is not newest first, loses a message that is still there, miscounts the matches, leaves a
  message that was deleted after the search as an error, when ``--unread-only`` or ``--since`` search for anything but
  the documented criterion, when a ``--since`` that is no age, or a search with no criterion, is not a JSON error before
  any search is sent, or when ``folders`` prints a name other than the one the server lists

[POS]
In-process listing test of the prebuilt skill script, next to ``test_imap_smtp_email_commands.py`` (the command lines
sent) and ``test_imap_smtp_email_failures.py`` (the failures after the connection is up).
"""

from __future__ import annotations

import json
from datetime import datetime, tzinfo
from types import ModuleType
from typing import Self
from unittest.mock import MagicMock, call

import pytest

from tests.support.email_skill_inprocess import imap_client, run_main

_NO_CRITERION = "At least one search criterion is required (--from, --subject, --to, --since, --keyword)"


class _NoonOnNov3(datetime):
    """The script's clock: 3 November 2026, 12:00."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls(2026, 11, 3, 12)


def _headers(uid: int, subject: str) -> bytes:
    return f"From: a@example.test\r\nSubject: {subject}\r\nMessage-ID: <{uid}@example.test>\r\n\r\n".encode()


def _summary(uid: int, subject: str) -> dict[str, object]:
    return {"uid": uid, "from": "a@example.test", "to": "", "subject": subject, "date": "", "message_id": f"<{uid}@example.test>"}


def _mailbox(stored: dict[int, bytes | None]) -> MagicMock:
    """An IMAP client whose search finds every UID of *stored* and whose header fetch returns that UID's headers.

    A UID stored as ``None`` is one the server returns nothing for, as for a message deleted since the search.
    """
    conn = imap_client()

    def uid(command: str, *args: str) -> tuple[str, list[object]]:
        if command == "search":
            return "OK", [" ".join(map(str, stored)).encode()]
        headers = stored[int(args[0])]
        return "OK", [None] if headers is None else [(b"1 (RFC822.HEADER)", headers), b")"]

    conn.uid.side_effect = uid
    return conn


def _printed(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], conn: MagicMock, *argv: str
) -> object:
    run_main(email_manager, monkeypatch, conn, *argv)
    return json.loads(capsys.readouterr().out)


def _failure_of(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], conn: MagicMock, *argv: str
) -> object:
    with pytest.raises(SystemExit) as exit_info:
        run_main(email_manager, monkeypatch, conn, *argv)
    assert exit_info.value.code == 1
    return json.loads(capsys.readouterr().out)["error"]


@pytest.mark.parametrize("command", [["check"], ["search", "--subject", "x"]], ids=["check", "search"])
def test_a_listing_is_newest_first_and_counts_every_match_beyond_the_limit(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    conn = _mailbox({3: _headers(3, "old"), 5: _headers(5, "middle"), 7: _headers(7, "new")})

    listing = _printed(email_manager, monkeypatch, capsys, conn, *command, "--limit", "2")

    assert listing == {"messages": [_summary(7, "new"), _summary(5, "middle")], "total": 3}


def test_a_message_deleted_after_the_search_is_left_out_of_the_listing_not_an_error(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = _mailbox({5: _headers(5, "kept"), 7: None})

    listing = _printed(email_manager, monkeypatch, capsys, conn, "check")

    assert listing == {"messages": [_summary(5, "kept")], "total": 2}


def test_unread_only_searches_for_the_unseen_messages(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = _mailbox({})

    listing = _printed(email_manager, monkeypatch, capsys, conn, "check", "--unread-only")

    assert listing == {"messages": [], "total": 0}
    assert conn.uid.call_args_list == [call("search", "(UNSEEN)")]


@pytest.mark.parametrize(
    ("argv", "criteria"),
    [
        pytest.param(["--since", "7d"], '(SINCE "27-Oct-2026")', id="days"),
        pytest.param(["--since", "24h"], '(SINCE "02-Nov-2026")', id="hours"),
        pytest.param(["--since", "2w"], '(SINCE "20-Oct-2026")', id="weeks"),
        pytest.param(["--since", " 7D "], '(SINCE "27-Oct-2026")', id="spaces-and-capital"),
        pytest.param(
            ["--from", "boss@company.com", "--since", "7d"],
            '(FROM "boss@company.com" SINCE "27-Oct-2026")',
            id="documented-example",
        ),
    ],
)
def test_since_turns_an_age_into_the_date_it_was_that_long_ago(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    criteria: str,
) -> None:
    monkeypatch.setattr(email_manager, "datetime", _NoonOnNov3)
    conn = _mailbox({})

    _printed(email_manager, monkeypatch, capsys, conn, "search", *argv)

    assert conn.uid.call_args_list == [call("search", criteria)]


@pytest.mark.parametrize("since", ["xd", "1.5h", "999999999999d"], ids=["no-number", "fraction", "beyond-the-calendar"])
def test_a_since_that_is_no_age_is_a_json_error_before_any_search_is_sent(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], since: str
) -> None:
    conn = _mailbox({})

    error = _failure_of(email_manager, monkeypatch, capsys, conn, "search", "--since", since)

    assert error == f"Invalid --since format: '{since}'. Use e.g. '7d', '24h', '2w'"
    conn.uid.assert_not_called()


def test_a_search_with_no_criterion_is_a_json_error_before_any_search_is_sent(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = _mailbox({})

    error = _failure_of(email_manager, monkeypatch, capsys, conn, "search")

    assert error == _NO_CRITERION
    conn.uid.assert_not_called()


def test_folders_prints_the_name_of_each_mailbox_the_server_lists(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    conn = imap_client()
    conn.list.return_value = (
        "OK",
        [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren) "/" "Sent Items"',
            b'(\\HasNoChildren) "/" &XfJT0ZAB-',
            b'(\\Noselect \\HasChildren) "/" "[Gmail]"',
        ],
    )

    listing = _printed(email_manager, monkeypatch, capsys, conn, "folders")

    assert listing == {"folders": ["INBOX", "Sent Items", "&XfJT0ZAB-", "[Gmail]"]}
