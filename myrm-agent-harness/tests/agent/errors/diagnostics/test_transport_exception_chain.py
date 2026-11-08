"""A connection failure is read through its cause chain for a rejected certificate.

[INPUT]
- agent.errors.diagnostics::LLMErrorDiagnostic, ErrorContext (POS: LLM error diagnostic engine)

[OUTPUT]
- Fails when a "Connection error." wrapper hides a rejected certificate from the diagnosis, when the chain is read
  for anything but a hard certificate signal, or when a wrapper that is not a connection failure loses its own verdict.

[POS]
Regression guard for the transport family of the diagnostic engine. The wrappers are linked the two ways a client
stack links them: an implicit ``__context__`` (raised inside an ``except``) and an explicit ``raise ... from``; httpx
and httpcore use the latter.
"""

from __future__ import annotations

import ssl
from typing import Literal

import httpcore
import httpx
import pytest

from myrm_agent_harness.agent.errors.diagnostics import ErrorContext, LLMErrorDiagnostic

_CERT = "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate (_ssl.c:1032)"
_CUSTOM_ENDPOINT = ErrorContext(model_name="m", is_custom_endpoint=True, base_url="https://llm.corp.example/v1")

_Link = Literal["cause", "context"]


def _wrap(cause: Exception, wrapper: Exception, link: _Link) -> Exception:
    """Link *wrapper* to *cause* as ``raise ... from`` (``cause``) or a raise inside ``except`` (``context``) does."""
    if link == "cause":
        wrapper.__cause__ = cause
    else:
        wrapper.__context__ = cause
    return wrapper


def _transport_chain(root: Exception) -> Exception:
    """The layers a model request raises on a failed connection, only the innermost carrying the reason."""
    error = _wrap(root, httpcore.ConnectError(""), "cause")
    return _wrap(error, httpx.ConnectError(""), "cause")


@pytest.mark.parametrize("link", ["cause", "context"])
@pytest.mark.parametrize("locale", ["en", "zh-CN"])
def test_a_connection_error_wrapping_a_rejected_certificate_is_diagnosed_as_the_certificate(
    link: _Link, locale: str
) -> None:
    bare = LLMErrorDiagnostic.diagnose(Exception(_CERT), locale=locale)
    wrapped = _wrap(ssl.SSLCertVerificationError(_CERT), Exception("Connection error."), link)

    assert bare.error_type == "tls_certificate"
    assert LLMErrorDiagnostic.diagnose(wrapped, locale=locale) == bare


def test_the_certificate_at_the_innermost_layer_of_the_transport_chain_is_found() -> None:
    wrapped = _transport_chain(ssl.SSLCertVerificationError(_CERT))

    assert LLMErrorDiagnostic.diagnose(wrapped, locale="en").error_type == "tls_certificate"


def test_a_custom_endpoint_with_a_rejected_certificate_is_not_reported_as_an_unreachable_service() -> None:
    wrapped = _transport_chain(ssl.SSLCertVerificationError(_CERT))

    assert LLMErrorDiagnostic.diagnose(wrapped, _CUSTOM_ENDPOINT, locale="en").error_type == "tls_certificate"


@pytest.mark.parametrize(
    "cause",
    [
        "[Errno 61] Connect call failed ('127.0.0.1', 11434)",
        "[Errno 8] nodename nor servname provided, or not known",
        # Phrases of the transient TLS list that also describe a plain-HTTP service or a dropped socket.
        "[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1032)",
        "[Errno 32] Broken pipe",
    ],
)
def test_a_connection_error_whose_cause_is_not_a_rejected_certificate_stays_a_connection_failure(cause: str) -> None:
    wrapped = _transport_chain(OSError(cause))

    assert LLMErrorDiagnostic.diagnose(wrapped, locale="en").error_type == "connection"
    assert (
        LLMErrorDiagnostic.diagnose(wrapped, _CUSTOM_ENDPOINT, locale="en").error_type == "custom_endpoint_unreachable"
    )


@pytest.mark.parametrize(
    ("outer", "verdict"),
    [
        ("Rate limit exceeded", "rate_limit"),
        ("Error code: 401 - invalid api key", "api_key"),
        ("Request timed out.", "timeout"),
    ],
)
def test_a_wrapper_that_is_not_a_connection_failure_keeps_its_own_verdict_whatever_it_wraps(
    outer: str, verdict: str
) -> None:
    wrapped = _wrap(ssl.SSLCertVerificationError(_CERT), Exception(outer), "context")

    assert LLMErrorDiagnostic.diagnose(wrapped, locale="en").error_type == verdict


def test_a_refused_connection_names_the_unreachable_service_not_a_timeout() -> None:
    """httpx words a refused connection "All connection attempts failed", which no keyword of ours matches."""
    refused = _wrap(
        ConnectionRefusedError(61, "Connect call failed"), httpx.ConnectError("All connection attempts failed"), "cause"
    )

    assert LLMErrorDiagnostic.diagnose(refused, locale="en").error_type == "connection"
    assert (
        LLMErrorDiagnostic.diagnose(refused, _CUSTOM_ENDPOINT, locale="en").error_type == "custom_endpoint_unreachable"
    )


@pytest.mark.parametrize("timeout", [httpx.ReadTimeout(""), httpx.ConnectTimeout("")])
def test_a_timed_out_request_is_a_timeout_even_on_a_custom_endpoint(timeout: Exception) -> None:
    assert LLMErrorDiagnostic.diagnose(timeout, _CUSTOM_ENDPOINT, locale="en").error_type == "timeout"
