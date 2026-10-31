"""Looking inside TLS contexts in the enterprise network compatibility unit tests."""

from __future__ import annotations

import ssl
from pathlib import Path

import pytest

STRICT_FLAG = getattr(ssl, "VERIFY_X509_STRICT", 0)

needs_strict_flag = pytest.mark.skipif(not STRICT_FLAG, reason="VERIFY_X509_STRICT not available (Python < 3.13)")


def is_truststore_context(ctx: ssl.SSLContext) -> bool:
    """Whether *ctx* verifies against the operating system's store, which ``truststore`` stands in for."""
    return type(ctx).__module__.startswith("truststore")


def loaded_cas(ctx: ssl.SSLContext) -> list[bytes]:
    """The CA certificates loaded into *ctx* itself, not the ones the operating system holds."""
    return ctx.get_ca_certs(binary_form=True)


def der_of(pem_file: Path) -> bytes:
    return ssl.PEM_cert_to_DER_cert(pem_file.read_text())
