"""Whether an LLM call failed because the server's certificate was rejected.

[INPUT]
- infra.tls_compat::is_tls_hard_error (POS: Enterprise TLS compatibility)
- errors.error_payload::walk_exception_chain (POS: The one reader of the provider's answer in an LLM exception)
- errors.normalize::extract_status_code (POS: Input stage of the failure classifier)

[OUTPUT]
- CONNECTION_KEYWORDS: the wordings of a connection that failed before any answer came back
- rejects_certificate: whether an LLM exception means the server's certificate was rejected, however many client
  layers wrap it; never true for a 4xx answer, which proves the handshake succeeded

[POS]
The one verdict on a rejected certificate, shared by the failure classifier (retry, key rotation and failover
decisions) and the error diagnostics (the card the user reads), so the two can never name different causes for the
same exception.
"""

from __future__ import annotations

from myrm_agent_harness.infra.tls_compat import is_tls_hard_error

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

    *text* is the caller's lower-cased reading of the exception's own wording; a hard signal there is the verdict.
    A client library words the same failure as a bare "Connection error." and keeps the reason in the cause chain,
    so a connection failure is also read through its causes. Only hard signals are read through the chain: the
    transient ones include protocol-agnostic phrases ("wrong version number", "broken pipe"), which would turn an
    https URL pointed at a plain-HTTP service into a rejected certificate.

    A 4xx status is an answer the server sent over a finished handshake, so it can never be a rejected certificate,
    however its body is worded: a provider echoes the offending request, which may quote any certificate error.
    """
    status = extract_status_code(exc)
    if status is not None and 400 <= status < 500:
        return False
    if is_tls_hard_error(text):
        return True
    return any(keyword in text for keyword in CONNECTION_KEYWORDS) and any(
        is_tls_hard_error(str(cause)) for cause in walk_exception_chain(exc)[1:]
    )
