"""A rejected certificate is one verdict across the failure classifier.

[INPUT]
- toolkits.llms.errors.classifier::classify_error, classify_failover_reason (POS: LLM error classification)
- toolkits.llms.errors.tls_rejection::rejects_certificate (POS: The one verdict on a rejected certificate)
- toolkits.llms.errors.error_payload::MAX_CHAIN_DEPTH, walk_exception_chain (POS: The one reader of the provider's answer)

[OUTPUT]
- Fails when a rejected certificate is filed under another failure (retried, rotated against a key, cooled as a
  rate limit), when a 4xx answer that merely quotes a certificate error is taken for one, or when the root cause of a
  deep client chain is no longer read.

[POS]
Unit tests of the certificate verdict on hand-built exception chains; the real client stacks are pinned by
``tests/integration/test_tls_certificate_rejection_integration.py``.
"""

import ssl

import pytest

from myrm_agent_harness.toolkits.llms.errors.classifier import (
    ErrorKind,
    classify_error,
    classify_failover_reason,
)
from myrm_agent_harness.toolkits.llms.errors.error_payload import MAX_CHAIN_DEPTH, walk_exception_chain
from myrm_agent_harness.toolkits.llms.errors.error_types import FailoverReason, RecoverabilityLevel, get_probe_policy
from myrm_agent_harness.toolkits.llms.errors.tls_rejection import rejects_certificate

# ============================================================================
# classify_error — hard TLS failure (rejected certificate, fail-fast)
# ============================================================================


@pytest.mark.parametrize(
    "msg",
    [
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate",
        "unable to get local issuer certificate",
        "unable to verify the first certificate",
        "hostname mismatch, certificate is not valid for 'api.example.com'",
        "certificate has expired",
    ],
)
def test_classify_tls_hard_as_tls_certificate(msg: str) -> None:
    assert classify_failover_reason(Exception(msg)) == FailoverReason.TLS_CERTIFICATE
    assert classify_error(Exception(msg)) == ErrorKind.TLS_CERTIFICATE


@pytest.mark.parametrize(
    "msg",
    [
        # Spellings that differ from another signal only in a separator or an apostrophe.
        "Error: DEPTH_ZERO_SELF_SIGNED_CERT",
        "SELF_SIGNED_CERT_IN_CHAIN",
        "Hostname doesn\u2019t match certificate",
        "basic_constraints of CA cert",
        # Wordings the classifier once missed: the code alone, an expiry in Node's short form.
        "[SSL: CERTIFICATE_VERIFY_FAILED]",
        "cert has expired",
    ],
)
def test_classify_tls_hard_spellings_as_tls_certificate(msg: str) -> None:
    assert classify_error(Exception(msg)) == ErrorKind.TLS_CERTIFICATE


_CERT = "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate (_ssl.c:1032)"


def _wrapped_in_connection_error(root: Exception, outermost: str) -> Exception:
    """A client library's layers around *root*: only the innermost carries the reason, the outermost is its wording."""
    middle = ConnectionError("Connection error.")
    middle.__cause__ = root
    outer = Exception(outermost)
    outer.__context__ = middle
    return outer


@pytest.mark.parametrize(
    "outermost",
    [
        "litellm.InternalServerError: OpenAIException - Connection error.",
        "litellm.InternalServerError: VertexAIException - Connection error",
        "litellm.APIConnectionError: Connection error.",
    ],
)
def test_classify_connection_error_wrapping_a_rejected_certificate(outermost: str) -> None:
    exc = _wrapped_in_connection_error(ssl.SSLCertVerificationError(1, _CERT), outermost)
    assert classify_failover_reason(exc) == FailoverReason.TLS_CERTIFICATE
    assert classify_error(exc) == ErrorKind.TLS_CERTIFICATE


def test_classify_certificate_inside_a_connection_error_class_name_is_not_a_timeout() -> None:
    """The class name's "connection error" alone would file the rejection under the timeout rule."""
    exc = Exception(f"litellm.APIConnectionError: {_CERT}")
    assert classify_failover_reason(exc) == FailoverReason.TLS_CERTIFICATE


@pytest.mark.parametrize(
    "root",
    [
        ConnectionRefusedError(61, "Connection refused"),
        OSError(8, "nodename nor servname provided, or not known"),
        ssl.SSLError(1, "[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1032)"),
        BrokenPipeError(32, "Broken pipe"),
        ssl.SSLEOFError(8, "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"),
    ],
    ids=["refused", "dns", "wrong_version", "broken_pipe", "eof"],
)
def test_classify_connection_error_without_a_rejected_certificate_stays_transient(root: Exception) -> None:
    """An https URL pointed at a plain-HTTP service or an interrupted handshake is no certificate verdict."""
    exc = _wrapped_in_connection_error(root, "litellm.InternalServerError: OpenAIException - Connection error.")
    assert classify_failover_reason(exc) == FailoverReason.TIMEOUT


def test_a_rejected_certificate_is_permanent_failoverable_and_probed_on_the_timeout_schedule() -> None:
    """No retry changes the verdict, a backup endpoint may still answer, and the user can fix the trust setup."""
    assert FailoverReason.TLS_CERTIFICATE.recoverability is RecoverabilityLevel.PERMANENT
    assert FailoverReason.TLS_CERTIFICATE.is_failoverable
    assert ErrorKind.TLS_CERTIFICATE.is_failoverable
    assert ErrorKind.TLS_CERTIFICATE.to_failover_reason() is FailoverReason.TLS_CERTIFICATE
    assert get_probe_policy(FailoverReason.TLS_CERTIFICATE) == get_probe_policy(FailoverReason.TIMEOUT)


class _AnswerError(Exception):
    """An SDK exception that carries the status of the answer the server sent."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422, 429])
def test_a_4xx_answer_is_never_a_rejected_certificate(status: int) -> None:
    """The server answered over a finished handshake; its body may still quote a certificate error."""
    exc = _AnswerError(f"Error code: {status} - invalid input: {_CERT}", status)

    assert not rejects_certificate(exc, str(exc).lower())
    assert classify_error(exc) is not ErrorKind.TLS_CERTIFICATE
    assert classify_failover_reason(exc) is not FailoverReason.TLS_CERTIFICATE


@pytest.mark.parametrize("status", [500, 502])
def test_a_rejection_a_gateway_relays_in_a_5xx_is_still_a_rejected_certificate(status: int) -> None:
    exc = _AnswerError(f"upstream request failed: {_CERT}", status)

    assert rejects_certificate(exc, str(exc).lower())
    assert classify_error(exc) is ErrorKind.TLS_CERTIFICATE


def _chain_of(root: Exception, links: int) -> Exception:
    """An exception whose chain holds *links* exceptions: *root* at the bottom, a client library's wording on top."""
    current = root
    for _ in range(links - 3):
        layer = ConnectionError("Connection error.")
        layer.__cause__ = current
        current = layer
    return _wrapped_in_connection_error(current, "litellm.InternalServerError: OpenAIException - Connection error.")


@pytest.mark.parametrize("links", [3, 7, MAX_CHAIN_DEPTH])
def test_the_rejected_certificate_is_found_at_any_depth_up_to_the_bound(links: int) -> None:
    exc = _chain_of(ssl.SSLCertVerificationError(1, _CERT), links)

    assert len(walk_exception_chain(exc)) == links
    assert classify_error(exc) is ErrorKind.TLS_CERTIFICATE


def test_a_cause_beyond_the_bound_is_not_read() -> None:
    exc = _chain_of(ssl.SSLCertVerificationError(1, _CERT), MAX_CHAIN_DEPTH + 1)

    assert classify_error(exc) is ErrorKind.TIMEOUT
