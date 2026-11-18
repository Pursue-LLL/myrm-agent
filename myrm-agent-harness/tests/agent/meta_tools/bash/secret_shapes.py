"""Secret-shaped text for the output tests: a key block whose body no single-line rule recognises, and a form body of credential keys."""

from __future__ import annotations

import base64
import random

FORM_KEYS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "client_secret",
    "private_key",
    "auth_token",
    "session_token",
    "credentials",
    "passphrase",
    "db_password",
    "aws_secret_access_key",
    "github_token",
    "slack_token",
    "webhook_secret",
    "signing_key",
)

KEY_KINDS = (
    "RSA PRIVATE KEY",
    "PRIVATE KEY",
    "OPENSSH PRIVATE KEY",
    "EC PRIVATE KEY",
    "ENCRYPTED PRIVATE KEY",
    "DSA PRIVATE KEY",
)


def key_body(lines: int = 51) -> list[str]:
    """Lines of base64 as wide as a PEM body (64 characters) and as random: an entropy rule has no pattern to find in them."""
    rng = random.Random(20261118)
    return [base64.b64encode(rng.randbytes(48)).decode() for _ in range(lines)]


def key_block(kind: str = "RSA PRIVATE KEY", *, body: list[str] | None = None) -> list[str]:
    """The lines of a private key block: the opening line, the body (51 lines unless given), the closing line."""
    return [f"-----BEGIN {kind}-----", *(key_body() if body is None else body), f"-----END {kind}-----"]
