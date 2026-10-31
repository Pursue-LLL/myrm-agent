"""Whether an LLM call failed because the server's certificate was rejected.

[INPUT]
- infra.tls_error_signals::is_tls_hard_error (POS: The one list of certificate-rejection and interrupted-handshake wordings)
- errors.error_payload::walk_exception_chain (POS: The one reader of the provider's answer in an LLM exception)
- errors.normalize::extract_status_code (POS: Input stage of the failure classifier)

[OUTPUT]
- CONNECTION_KEYWORDS: the wordings of a connection that failed before any answer came back
- rejects_certificate: whether an LLM exception means the server's certificate was rejected, however many client
  layers wrap it and in whatever language the operating system worded it; never true for a 4xx answer, which proves
  the handshake succeeded, nor for a wrapper that states another verdict (rate limit, rejected key, timeout)

[POS]
The one verdict on a rejected certificate, shared by the failure classifier (retry, key rotation and failover
decisions) and the error diagnostics (the card the user reads), so the two can never name different causes for the
same exception.
"""

from __future__ import annotations

import ssl

from myrm_agent_harness.infra.tls_error_signals import is_tls_hard_error

from .error_payload import walk_exception_chain
from .normalize import extract_status_code

CONNECTION_KEYWORDS = (
    "connection refused",
    "connection reset",
    "connection error",
    "failed to establish",
)


def rejects_certificate(exc: Exception, text: str) -> bool:
    """True when *exc* failed because the server's certificate was rejected.

    A hard signal in *text*, the caller's lower-cased reading of the exception's own wording, is the verdict. A client
    library words the same failure as a bare "Connection error." and keeps the reason in the cause chain, so a
    connection failure is also read through its causes. Only hard signals are read through the chain: the transient
    ones include protocol-agnostic phrases ("wrong version number", "broken pipe"), which would turn an https URL
    pointed at a plain-HTTP service into a rejected certificate.

    A verifier that asks the operating system for its trust store (the enterprise compatibility mode) words the
    failure in the system's own language, so there is no text to match; there the exception's type decides: an
    ``ssl.SSLCertVerificationError`` is a rejected certificate when it is the exception itself or when the layers
    above it add no wording of their own (a connection failure, or a message that repeats the cause's). A wrapper
    that says something else (a rate limit, a rejected key, a timeout) keeps its own verdict whatever it wraps.

    A 4xx status is an answer the server sent over a finished handshake, so it can never be a rejected certificate,
    however its body is worded: a provider echoes the offending request, which may quote any certificate error.
    """
    status = extract_status_code(exc)
    if status is not None and 400 <= status < 500:
        return False
    if is_tls_hard_error(text):
        return True
    chain = walk_exception_chain(exc)
    is_connection_failure = any(keyword in text for keyword in CONNECTION_KEYWORDS)
    if any(
        isinstance(cause, ssl.SSLCertVerificationError)
        and (cause is exc or is_connection_failure or _repeats(text, cause))
        for cause in chain
    ):
        return True
    return is_connection_failure and any(is_tls_hard_error(str(cause)) for cause in chain[1:])


def _repeats(text: str, cause: Exception) -> bool:
    """Whether *text* carries the cause's message, i.e. the outer layer only relays it."""
    message = str(cause).lower()
    return bool(message) and message in text
