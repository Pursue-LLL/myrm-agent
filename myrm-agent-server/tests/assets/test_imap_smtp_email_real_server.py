"""The imap-smtp-email skill script against a real IMAP/SMTP server, the way a skill run starts it (no model involved).

The other tests of the script talk to doubles that answer what the script expects. This one talks to GreenMail over
implicit TLS with a certificate the script has to trust through ``SSL_CERT_FILE``, so what the server really sends back
and really accepts is what the commands are held to.

[INPUT]
- tests/support/greenmail_mailbox.py: the server, the PEM bundle that trusts it, the way mail gets in and out
- tests/support/email_skill_script.py: run_email_script, the child process with the variables a skill run injects

[OUTPUT]
- Fails when check, search or read do not find the mail the server holds, or when send or reply give the server a message
  that is not dated, not threaded on the mail it answers, or has an id that is not on the sender's domain.

[POS]
Real-server test of the prebuilt skill ``imap-smtp-email``, kept out of the default run (it needs Docker and the host's
port 465); the model-driven version of the same path is tests/api/agent/test_imap_smtp_email_skill_e2e.py.
"""

from __future__ import annotations

import email.message
import email.utils
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.support.email_skill_script import run_email_script
from tests.support.greenmail_mailbox import SMTP_TLS_HOST_PORT, Mailbox, deliver, messages_of, running_mailbox

pytestmark = pytest.mark.e2e

_SENDER_DOMAIN = "mail.example.test"
_USER = "alice@localhost"
_FIGURE = "FIG-90817"


@pytest.fixture(scope="module")
def mailbox(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Mailbox]:
    with running_mailbox(tmp_path_factory.mktemp("greenmail")) as running:
        yield running


def _run(tmp_path: Path, mailbox: Mailbox, *args: str, user: str = _USER) -> dict[str, object]:
    """One command, with the mailbox login in the process environment as the skill settings page injects it."""
    proc = run_email_script(
        tmp_path,
        list(args),
        port=mailbox.imap_port,
        trust=mailbox.ca_bundle,
        extra_env={
            "EMAIL_IMAP_HOST": mailbox.host,
            "EMAIL_IMAP_USER": user,
            "EMAIL_IMAP_PASSWORD": "pw",
            "EMAIL_SMTP_HOST": mailbox.host,
            "EMAIL_SMTP_PORT": str(SMTP_TLS_HOST_PORT),
            "EMAIL_FROM_ADDRESS": f"Alice <alice@{_SENDER_DOMAIN}>",
        },
    )
    assert proc.returncode == 0, f"{args[0]} failed: {proc.stderr[-400:]}"
    output: dict[str, object] = json.loads(proc.stdout)
    return output


def _incoming(sender: str, user: str, token: str) -> email.message.EmailMessage:
    message = email.message.EmailMessage()
    message["From"] = f"Bob Builder <{sender}>"
    message["To"] = user
    message["Subject"] = f"Quarterly numbers {token}"
    message["Message-ID"] = f"<incoming-{token}@localhost>"
    message.set_content(f"Hi Alice,\nthe Q3 figure is {_FIGURE}.\n")
    return message


def _the_only_message(listing: dict[str, object]) -> dict[str, object]:
    messages = listing["messages"]
    assert isinstance(messages, list) and len(messages) == 1, f"expected the one delivered mail, got {listing}"
    message = messages[0]
    assert isinstance(message, dict)
    return message


def test_check_search_and_read_find_the_mail_the_server_holds(tmp_path: Path, mailbox: Mailbox) -> None:
    user = "reader@localhost"
    deliver(mailbox, _incoming("bob-read@localhost", user, "R-1001"))

    listed = _the_only_message(_run(tmp_path, mailbox, "check", user=user))
    assert listed["subject"] == "Quarterly numbers R-1001"
    assert "bob-read@localhost" in str(listed["from"])

    found = _the_only_message(_run(tmp_path, mailbox, "search", "--from", "bob-read@localhost", user=user))
    assert found["uid"] == listed["uid"]

    read = _run(tmp_path, mailbox, "read", str(listed["uid"]), user=user)
    assert _FIGURE in str(read["body"])


def test_reply_is_threaded_dated_and_on_the_senders_domain(tmp_path: Path, mailbox: Mailbox) -> None:
    user = "replier@localhost"
    deliver(mailbox, _incoming("bob-reply@localhost", user, "R-2002"))
    uid = _the_only_message(_run(tmp_path, mailbox, "check", user=user))["uid"]

    sent = _run(tmp_path, mailbox, "reply", "--uid", str(uid), "--body", "Received, thanks", user=user)

    (reply,) = messages_of(mailbox, "bob-reply@localhost")
    assert sent["status"] == "sent" and reply["Message-ID"] == sent["message_id"]
    assert reply["Subject"] == "Re: Quarterly numbers R-2002"
    assert reply["In-Reply-To"] == "<incoming-R-2002@localhost>"
    assert reply["References"] == "<incoming-R-2002@localhost>"
    assert str(reply["Message-ID"]).endswith(f"@{_SENDER_DOMAIN}>")
    assert reply["Date"], "the reply has no Date header"
    sent_at = email.utils.parsedate_to_datetime(str(reply["Date"]))
    assert sent_at.tzinfo is not None and abs(datetime.now(UTC) - sent_at) < timedelta(minutes=5)
    body = reply.get_body(preferencelist=("plain",))
    assert body is not None and "Received, thanks" in body.get_content()


def test_send_is_dated_and_on_the_senders_domain(tmp_path: Path, mailbox: Mailbox) -> None:
    sent = _run(tmp_path, mailbox, "send", "--to", "carol-send@localhost", "--subject", "Hello", "--body", "Plain body")

    (message,) = messages_of(mailbox, "carol-send@localhost")
    assert message["Message-ID"] == sent["message_id"]
    assert str(message["Message-ID"]).endswith(f"@{_SENDER_DOMAIN}>")
    assert message["Date"], "the message has no Date header"
    assert email.utils.parsedate_to_datetime(str(message["Date"])).tzinfo is not None
    assert message["From"].addresses[0].addr_spec == f"alice@{_SENDER_DOMAIN}"
