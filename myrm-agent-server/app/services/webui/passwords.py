"""Password hashing helpers for WebUI admin (stdlib only)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_DKLEN,
    )
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"scrypt${salt_b64}${digest_b64}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, digest_b64 = stored.split("$", 2)
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    try:
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    except (ValueError, binascii.Error):
        return False

    try:
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_DKLEN,
        )
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


__all__ = ["hash_password", "verify_password"]
