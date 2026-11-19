"""A self-signed loopback certificate for tests that need a peer no default trust store accepts.

[INPUT]
(none; the ``cryptography`` package builds the certificate)

[OUTPUT]
- self_signed_certificate: writes a certificate valid for one host (``127.0.0.1`` unless a test names another, as an IP
  or a DNS name) and its private key, returns both file paths

[POS]
Server pytest-only helper shared by the tests that start a TLS listener on the loopback address. The listener's
certificate is its own issuer, so a client rejects it (``verify_code`` 18) until a test names the certificate file as
its trust. A certificate issued for a DNS name carries no IP address, so a client that connects by IP and checks the
name it was told passes only with that name.
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def _subject_alternative_name(host: str) -> x509.GeneralName:
    try:
        return x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:
        return x509.DNSName(host)


def self_signed_certificate(directory: Path, host: str = "127.0.0.1") -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([_subject_alternative_name(host)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    certificate_file, key_file = directory / "listener.pem", directory / "listener.key"
    certificate_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return certificate_file, key_file
