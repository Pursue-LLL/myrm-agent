"""A reply sent by the imap-smtp-email skill script goes to the sender, threads on the message and keeps its subject.

The message being answered is untrusted. A header with raw 8-bit bytes comes back from the parser as a ``Header`` object,
not a ``str``, and a subject can hold encoded words next to plain text; the reply is written to a third party, so what
it carries has to be a valid header either way.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: email_manager.py imported in process
- tests/assets/conftest.py: the script import path and the settings ``reply`` needs
- tests/support/email_skill_inprocess.py: the IMAP double and the in-process ``main``

[OUTPUT]
- Fails when a reply to a sender whose name is raw UTF-8 does not go to that sender's address, when a header that lists
  several addresses does not send the reply to all of them or ``Reply-To`` does not come before ``From``, when an empty
  ``Reply-To`` does not leave the reply to ``From`` or a message that holds no address in either is not refused before
  anything is sent, when an id with raw 8-bit bytes is written into ``In-Reply-To`` or ``References`` or takes the ASCII
  ids with it, when the ids of a clean message change, or when the subject of a reply changes its spacing

[POS]
In-process test of what ``reply`` sends, next to ``test_imap_smtp_email_failures.py``, which covers how it fails.
"""

from __future__ import annotations

import email
import email.header
import email.message
import email.utils
import json
from types import ModuleType

import pytest

from tests.support.email_skill_inprocess import conn_serving, run_main

_REPLY = ["reply", "--uid", "1", "--body", "b"]


def _reply_to(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outgoing_mail: list[bytes],
    stored: dict[str, str],
) -> tuple[dict[str, str], email.message.Message]:
    """Reply to a stored message with the headers *stored* added to defaults; the script's answer and the message it sent."""
    headers = {"From": "eve@example.test", "Subject": "invoice", "Message-ID": "<1@example.test>", **stored}
    raw = "".join(f"{name}: {value}\r\n" for name, value in headers.items()).encode() + b"\r\nbody\r\n"

    run_main(email_manager, monkeypatch, conn_serving(raw), *_REPLY)

    return json.loads(capsys.readouterr().out), email.message_from_bytes(outgoing_mail[0])


@pytest.mark.parametrize(
    "sender",
    [
        pytest.param({"From": "发票 <a@b.test>"}, id="from"),
        pytest.param({"Reply-To": "发票 <a@b.test>"}, id="reply-to"),
    ],
)
def test_a_reply_goes_to_the_address_of_a_sender_whose_name_is_raw_utf_8(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outgoing_mail: list[bytes],
    sender: dict[str, str],
) -> None:
    """Raw UTF-8 in the header makes the parser return a ``Header`` object, which ``parseaddr`` cannot read as an address."""
    answer, _sent = _reply_to(email_manager, monkeypatch, capsys, outgoing_mail, sender)

    assert answer["to"] == "a@b.test"


@pytest.mark.parametrize(
    ("stored", "to"),
    [
        pytest.param({"Reply-To": "a@x.test, b@y.test"}, "a@x.test, b@y.test", id="two-reply-to-addresses"),
        pytest.param({"Reply-To": "Ann <a@x.test>, 发票 <b@y.test>"}, "a@x.test, b@y.test", id="names-and-raw-utf-8"),
        pytest.param({"Reply-To": "Team: a@x.test, b@y.test;"}, "a@x.test, b@y.test", id="a-group"),
        pytest.param({"From": "a@x.test, b@y.test"}, "a@x.test, b@y.test", id="two-senders"),
        pytest.param({"From": "a@x.test, b@y.test", "Reply-To": "c@z.test"}, "c@z.test", id="reply-to-wins"),
    ],
)
def test_a_reply_goes_to_every_address_of_the_header_it_follows(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outgoing_mail: list[bytes],
    stored: dict[str, str],
    to: str,
) -> None:
    """A header can list several addresses, written in a group or not, and a mail client answers every one of them."""
    answer, sent = _reply_to(email_manager, monkeypatch, capsys, outgoing_mail, stored)

    assert answer["to"] == to
    assert [address for _, address in email.utils.getaddresses([sent["To"]])] == to.split(", ")


@pytest.mark.parametrize(
    "reply_to", ["", "   ", "<>", "undisclosed-recipients:;"], ids=["empty", "spaces", "no-address", "empty-group"]
)
def test_a_reply_goes_to_the_sender_when_reply_to_holds_no_address(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outgoing_mail: list[bytes],
    reply_to: str,
) -> None:
    """Automated mail often carries an empty ``Reply-To``; a mail client answers the ``From`` then, and so must the script."""
    answer, sent = _reply_to(email_manager, monkeypatch, capsys, outgoing_mail, {"Reply-To": reply_to})

    assert answer["to"] == "eve@example.test"
    assert sent["To"] == "eve@example.test"


@pytest.mark.parametrize(
    "stored",
    [{"From": ""}, {"From": "", "Reply-To": " "}, {"From": "<>", "Reply-To": "<>"}],
    ids=["no-sender", "neither-header-holds-an-address", "no-address-in-either"],
)
def test_a_message_that_names_no_address_is_refused_and_nothing_is_sent(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outgoing_mail: list[bytes],
    stored: dict[str, str],
) -> None:
    """A recipient list holding an empty address would send ``RCPT TO:<>`` to the server."""
    with pytest.raises(SystemExit):
        _reply_to(email_manager, monkeypatch, capsys, outgoing_mail, stored)

    assert json.loads(capsys.readouterr().out) == {"error": "The message has no Reply-To or From address to reply to"}
    assert outgoing_mail == []


@pytest.mark.parametrize(
    ("stored", "in_reply_to", "references"),
    [
        pytest.param({"References": "<0@example.test>"}, "<1@example.test>", "<0@example.test> <1@example.test>", id="ascii-ids"),
        pytest.param(
            {"Message-ID": "<发票@example.test>", "References": "<0@example.test>"}, None, "<0@example.test>", id="message-id"
        ),
        pytest.param(
            {"References": "<ok@example.test> <发票@example.test>"},
            "<1@example.test>",
            "<ok@example.test> <1@example.test>",
            id="one-reference",
        ),
    ],
)
def test_a_reply_threads_on_the_ids_a_header_can_carry(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outgoing_mail: list[bytes],
    stored: dict[str, str],
    in_reply_to: str | None,
    references: str,
) -> None:
    """An id with raw UTF-8 would be written as an encoded word, which a threading header must not hold (RFC 2047 §5)."""
    _answer, sent = _reply_to(email_manager, monkeypatch, capsys, outgoing_mail, stored)

    assert sent.get("In-Reply-To") == in_reply_to
    assert sent["References"] == references


@pytest.mark.parametrize(
    ("stored", "subject"),
    [
        pytest.param("=?UTF-8?B?5Y+R56Wo?=", "Re: 发票", id="encoded-word-only"),
        pytest.param("Re: =?UTF-8?B?5Y+R56Wo?=", "Re: 发票", id="text-before-an-encoded-word"),
        pytest.param("Fwd: =?UTF-8?B?5Y+R56Wo?= - 2026", "Re: Fwd: 发票 - 2026", id="encoded-word-between-text"),
    ],
)
def test_the_subject_of_a_reply_keeps_the_spacing_of_the_subject_it_answers(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outgoing_mail: list[bytes],
    stored: str,
    subject: str,
) -> None:
    answer, sent = _reply_to(email_manager, monkeypatch, capsys, outgoing_mail, {"Subject": stored})

    assert answer["subject"] == subject
    assert str(email.header.make_header(email.header.decode_header(sent["Subject"]))) == subject
