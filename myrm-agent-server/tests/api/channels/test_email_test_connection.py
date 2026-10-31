"""The email connection test verifies the server certificate, gives up on a silent server and reports why it failed.

``imaplib.IMAP4_SSL`` is replaced by an ``autospec`` double, so a keyword the real constructor does not accept raises
``TypeError`` instead of being swallowed, and the arguments the endpoint passes are read back from the call.
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.channels.test_connections import _IMAP_TEST_TIMEOUT
from tests.support.minimal_app import build_minimal_app

_URL = "/api/v1/channels/manage/email/test"
_BODY = {"imapHost": "imap.example.com", "username": "bot@example.com", "password": "secret"}

app = build_minimal_app(preset="channels_local")


@asynccontextmanager
async def _noop_lifespan(_app: object) -> AsyncIterator[None]:
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.router.lifespan_context = original_lifespan


@pytest.fixture
def imap() -> Iterator[MagicMock]:
    with patch("imaplib.IMAP4_SSL", autospec=True) as client:
        yield client


def test_the_server_is_checked_over_a_verified_connection_that_times_out(client: TestClient, imap: MagicMock) -> None:
    response = client.post(_URL, json={**_BODY, "imapPort": 1993})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "IMAP connection successful"}
    args, kwargs = imap.call_args
    assert args == ("imap.example.com", 1993)
    context = kwargs["ssl_context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert kwargs["timeout"] == _IMAP_TEST_TIMEOUT
    imap.return_value.login.assert_called_once_with("bot@example.com", "secret")


@pytest.mark.parametrize(
    ("failure", "reported"),
    [
        (
            ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate"),
            "CERTIFICATE_VERIFY_FAILED",
        ),
        (TimeoutError("timed out"), "timed out"),
        (ConnectionRefusedError("refused"), "refused"),
    ],
    ids=["rejected_certificate", "silent_server", "refused"],
)
def test_a_connection_that_cannot_be_made_is_reported(
    client: TestClient, imap: MagicMock, failure: OSError, reported: str
) -> None:
    imap.side_effect = failure

    response = client.post(_URL, json=_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert reported in body["message"]
