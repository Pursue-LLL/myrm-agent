"""Every IMAP and SMTP connection of the mail channel verifies the server certificate and gives up on a silent server.

The client classes are replaced by ``autospec`` doubles: a keyword the real constructor does not accept (``context=``
where imaplib wants ``ssl_context=``) raises ``TypeError`` instead of being swallowed, and the arguments the channel
passes are read back from the call.
"""

from __future__ import annotations

import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.channels.providers.email.channel import _SOCKET_TIMEOUT
from tests.channels.providers.email.email_channel_factory import make_channel


def _assert_verifies_the_server(context: object) -> None:
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


@pytest.fixture
def imap() -> Iterator[MagicMock]:
    with patch("imaplib.IMAP4_SSL", autospec=True) as client:
        client.return_value.uid.return_value = ("OK", [b""])
        yield client


@contextmanager
def _smtp_client(name: str) -> Iterator[MagicMock]:
    """Replace ``smtplib.<name>``; ``with smtplib.<name>(...) as server`` then yields the double itself, so the calls
    on ``server`` are checked against the real signatures too."""
    with patch(f"smtplib.{name}", autospec=True) as client:
        client.return_value.__enter__.return_value = client.return_value
        yield client


class TestImapConnections:
    @pytest.mark.parametrize("operation", ["_imap_ping", "_fetch_new_emails"])
    def test_the_connection_verifies_the_server_and_times_out(self, imap: MagicMock, operation: str) -> None:
        getattr(make_channel(), operation)()

        imap.assert_called_once()
        args, kwargs = imap.call_args
        assert args == ("imap.example.com", 993)
        _assert_verifies_the_server(kwargs["ssl_context"])
        assert kwargs["timeout"] == _SOCKET_TIMEOUT


class TestSmtpConnections:
    def test_implicit_tls_on_port_465_verifies_the_server_and_times_out(self) -> None:
        channel = make_channel()
        channel._smtp_port = 465

        with _smtp_client("SMTP_SSL") as client:
            channel._smtp_send("user@example.com", "Subject", "<p>Body</p>")

        args, kwargs = client.call_args
        assert args == ("smtp.example.com", 465)
        _assert_verifies_the_server(kwargs["context"])
        assert kwargs["timeout"] == _SOCKET_TIMEOUT
        assert [call[0] for call in client.return_value.method_calls] == ["login", "send_message"]

    def test_starttls_verifies_the_server_before_the_credentials_are_sent(self) -> None:
        with _smtp_client("SMTP") as client:
            make_channel()._smtp_send("user@example.com", "Subject", "<p>Body</p>")

        args, kwargs = client.call_args
        assert args == ("smtp.example.com", 587)
        assert kwargs["timeout"] == _SOCKET_TIMEOUT
        server = client.return_value
        _assert_verifies_the_server(server.starttls.call_args.kwargs["context"])
        assert [call[0] for call in server.method_calls] == ["starttls", "login", "send_message"]
