"""Wordings of a rejected TLS certificate and of an interrupted TLS handshake.

A rejected certificate is permanent, since retrying cannot change the verdict, and an interrupted handshake is not,
so the two lists are kept apart and a hard signal always wins over a transient one.

[INPUT]
- (none: matching over text)

[OUTPUT]
- is_tls_hard_error(): whether an error text carries a certificate-rejection signal (the single signal list the LLM
  failure classifier and the error diagnostics both read)
- is_tls_transient_error(): whether an error text is an interrupted handshake with no certificate verdict

[POS]
The one list of certificate-rejection and interrupted-handshake wordings, read by the LLM failure classifier
(``toolkits/llms/errors/tls_rejection.py``) and the error diagnostics
(``agent/errors/diagnostics/transport_diagnosis.py``), so a failure is named the same way wherever it is read.
"""

from __future__ import annotations

# Hard TLS failure signals: the certificate/chain itself is rejected.
# These are permanent (fail-fast) — retrying cannot change the verdict.
# Python/OpenSSL strict-mode wordings come first, then the Bun/Node ones
# (e.g. "unable to verify the first certificate"), hostname/altname mismatch
# and an expired leaf — all deliberately hard. A wording that differs from
# another only in a separator or an apostrophe (the "self_signed" of Node's
# DEPTH_ZERO_SELF_SIGNED_CERT, a typographic apostrophe) is listed as its own signal.
_TLS_HARD_SIGNALS = (
    "basic constraints",
    "basicconstraints",
    "basic_constraints",
    "basic-constraints",
    "not marked critical",
    "certificate verify failed",
    "ssl: certificate_verify_failed",
    "unable to get local issuer",
    "[ssl: certificate_verify_failed]",
    "self-signed certificate in certificate chain",
    "self-signed",
    "self signed",
    "self_signed",
    "selfsigned",
    "unable to verify the first certificate",
    "hostname mismatch",
    "hostname doesn't match",
    "hostname doesn\u2019t match",
    "hostname doesnt match",
    "certificate has expired",
    "cert has expired",
    "certificate expired",
    "expired certificate",
    "err_tls_cert_altname_invalid",
    "altname",
)

# Transient TLS transport signals: the handshake was interrupted before any
# certificate verdict (weak network, proxy reset, Bun mislabel). Bun's
# "unknown certificate verification error" belongs here: it is emitted when
# the connection is reset mid-handshake, with no certificate ever rejected.
_TLS_TRANSIENT_PATTERNS = (
    "unknown certificate verification",
    "unknown_certificate_verification",
    "certificate verification error",
    "ssl routines",
    "handshake failure",
    "failure in handshake",
    "unexpected eof",
    "eof occurred in violation of protocol",
    "broken pipe",
    "wrong version number",
    "bad record mac",
    "decryption failed",
    "tlsv1 alert",
    "ssl3_read_bytes",
    "ssl3_write_bytes",
)


def is_tls_hard_error(error_message: str) -> bool:
    """Detect a permanent TLS failure (bad chain, not a flaky network).

    Covers the strict-mode, Bun, Node and OpenSSL wordings of a rejected certificate.
    Hard failures must fail fast with remediation — never retried.
    """
    lower = error_message.lower()
    return any(pattern in lower for pattern in _TLS_HARD_SIGNALS)


def is_tls_transient_error(error_message: str) -> bool:
    """Detect an interrupted TLS handshake with no certificate verdict.

    True when transport-level signals are present and no hard signal matches.
    Callers should treat this as retryable (same class as connection reset).
    """
    lower = error_message.lower()
    if any(pattern in lower for pattern in _TLS_HARD_SIGNALS):
        return False
    return any(pattern in lower for pattern in _TLS_TRANSIENT_PATTERNS)
