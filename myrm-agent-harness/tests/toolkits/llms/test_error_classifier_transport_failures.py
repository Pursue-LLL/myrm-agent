"""Failures of the HTTP connection itself classify as transport timeouts, whatever wording the client gives them."""

from __future__ import annotations

import ssl

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout(""),
        httpx.ConnectTimeout(""),
        httpx.PoolTimeout(""),
        httpx.WriteTimeout(""),
        httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known"),
        httpx.ReadError(""),
        httpx.RemoteProtocolError("peer closed connection without sending complete message body"),
    ],
    ids=lambda e: type(e).__name__,
)
def test_a_connection_level_failure_is_a_timeout(failure: httpx.TransportError) -> None:
    assert classify_error(failure) == ErrorKind.TIMEOUT


def test_a_wrapped_connection_failure_is_a_timeout() -> None:
    try:
        try:
            raise httpx.ReadTimeout("")
        except httpx.ReadTimeout as inner:
            raise RuntimeError("model call failed") from inner
    except RuntimeError as wrapped:
        assert classify_error(wrapped) == ErrorKind.TIMEOUT


def test_a_rejected_certificate_keeps_its_own_verdict() -> None:
    failure = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate")
    failure.__cause__ = ssl.SSLCertVerificationError("certificate verify failed")
    assert classify_error(failure) == ErrorKind.TLS_CERTIFICATE


def test_an_http_answer_is_never_read_as_a_transport_failure() -> None:
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(401, json={"error": {"message": "bad key"}}, request=request)
    error = LLMHTTPError("openai", 401, response.text, response)
    error.__context__ = httpx.ReadTimeout("")
    assert classify_error(error) == ErrorKind.AUTH
