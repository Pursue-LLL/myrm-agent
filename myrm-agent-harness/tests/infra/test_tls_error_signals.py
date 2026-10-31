"""Unit tests for infra/tls_error_signals.py: a rejected certificate and an interrupted handshake are told apart."""

from __future__ import annotations

import pytest

from myrm_agent_harness.infra.tls_error_signals import is_tls_hard_error, is_tls_transient_error


class TestIsTlsHardVsTransient:
    """Hard certificate rejections fail fast; interrupted handshakes retry."""

    @pytest.mark.parametrize(
        "msg",
        [
            # Real verified Python tracebacks (local socket reproduction).
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate",
            "unable to get local issuer certificate",
            "unable to verify the first certificate",
            "hostname mismatch, certificate is not valid for 'api.example.com'",
            "certificate has expired",
            "ERR_TLS_CERT_ALTNAME_INVALID",
            "BasicConstraints of CA cert not marked critical",
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
            "self-signed certificate in certificate chain",
            # The same wordings with another separator or apostrophe, and the codes Node and OpenSSL print alone.
            "Error: DEPTH_ZERO_SELF_SIGNED_CERT",
            "SELF_SIGNED_CERT_IN_CHAIN",
            "Hostname doesn\u2019t match certificate",
            "basic_constraints of CA cert",
            "[SSL: CERTIFICATE_VERIFY_FAILED]",
            "cert has expired",
            # OpenSSL 3 words a rejected chain with a transient marker ("ssl routines") in the same text.
            "error:0A000086:SSL routines:tls_post_process_server_certificate:certificate verify failed",
        ],
    )
    def test_hard_errors_fail_fast(self, msg: str) -> None:
        assert is_tls_hard_error(msg) is True
        assert is_tls_transient_error(msg) is False

    @pytest.mark.parametrize(
        "msg",
        [
            # Bun mislabel: reset mid-handshake, no certificate ever rejected.
            "unknown certificate verification error",
            "UNKNOWN_CERTIFICATE_VERIFICATION_ERROR",
            # Real verified Python tracebacks (local socket reproduction).
            "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol",
            "[Errno 32] Broken pipe",
            "ssl.SSLError: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] handshake failure",
        ],
    )
    def test_transient_errors_retryable(self, msg: str) -> None:
        assert is_tls_transient_error(msg) is True
        assert is_tls_hard_error(msg) is False

    @pytest.mark.parametrize(
        "msg",
        [
            "Connection refused",
            "DNS resolution failed",
            "Timeout exceeded",
            "Rate limit exceeded",
            "Invalid API key",
        ],
    )
    def test_ignores_non_tls_errors(self, msg: str) -> None:
        assert is_tls_transient_error(msg) is False
        assert is_tls_hard_error(msg) is False
