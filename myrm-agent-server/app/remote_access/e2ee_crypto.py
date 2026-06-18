"""NaCl box (Curve25519 + XSalsa20-Poly1305) primitives for remote-access E2EE.

Compatible with Paseo relay crypto: base64-encoded [nonce || ciphertext] bundles.

[INPUT]
- Raw bytes or base64-encoded ciphertext bundles

[OUTPUT]
- Encryption/decryption functions for E2EE payloads

[POS]
Pure crypto utilities. No I/O, no state. Used by e2ee_session and e2ee_response.
"""

from __future__ import annotations

import base64
import binascii
import secrets

from nacl.exceptions import CryptoError
from nacl.public import Box, PrivateKey, PublicKey

PUBLIC_KEY_BYTES = 32
NONCE_BYTES = 24


class E2EECryptoError(ValueError):
    """Invalid key material or ciphertext for E2EE operations."""


def generate_keypair() -> tuple[bytes, bytes]:
    """Return (public_key, secret_key) each 32 bytes."""
    private = PrivateKey.generate()
    return bytes(private.public_key), bytes(private)


def public_key_b64(public_key: bytes) -> str:
    if len(public_key) != PUBLIC_KEY_BYTES:
        raise E2EECryptoError("Invalid public key length")
    return base64.urlsafe_b64encode(public_key).decode("ascii").rstrip("=")


def public_key_from_b64(value: str) -> bytes:
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, ValueError) as exc:
        raise E2EECryptoError("Invalid base64 public key") from exc
    if len(raw) != PUBLIC_KEY_BYTES:
        raise E2EECryptoError("Invalid public key length")
    return raw


def open_box(
    *,
    secret_key: bytes,
    peer_public_key: bytes,
    bundle_b64: str,
) -> bytes:
    """Decrypt a base64 NaCl box bundle from ``peer_public_key``."""
    try:
        padded = bundle_b64 + "=" * (-len(bundle_b64) % 4)
        bundle = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, ValueError) as exc:
        raise E2EECryptoError("Invalid base64 ciphertext") from exc
    if len(bundle) < NONCE_BYTES + 16:
        raise E2EECryptoError("Ciphertext too short")
    box = Box(PrivateKey(secret_key), PublicKey(peer_public_key))
    try:
        return box.decrypt(bundle)
    except CryptoError as exc:
        raise E2EECryptoError("Decryption failed") from exc


def seal_box(
    *,
    secret_key: bytes,
    peer_public_key: bytes,
    plaintext: bytes,
) -> str:
    """Encrypt ``plaintext`` for ``peer_public_key``; return urlsafe base64 bundle."""
    box = Box(PrivateKey(secret_key), PublicKey(peer_public_key))
    bundle = box.encrypt(plaintext)
    return base64.urlsafe_b64encode(bundle).decode("ascii").rstrip("=")


def encrypt_utf8(*, secret_key: bytes, peer_public_key: bytes, text: str) -> str:
    return seal_box(
        secret_key=secret_key,
        peer_public_key=peer_public_key,
        plaintext=text.encode("utf-8"),
    )


def decrypt_utf8(*, secret_key: bytes, peer_public_key: bytes, bundle_b64: str) -> str:
    return open_box(
        secret_key=secret_key,
        peer_public_key=peer_public_key,
        bundle_b64=bundle_b64,
    ).decode("utf-8")


def new_session_id() -> str:
    return secrets.token_urlsafe(24)


__all__ = [
    "E2EECryptoError",
    "NONCE_BYTES",
    "PUBLIC_KEY_BYTES",
    "decrypt_utf8",
    "encrypt_utf8",
    "generate_keypair",
    "new_session_id",
    "open_box",
    "public_key_b64",
    "public_key_from_b64",
    "seal_box",
]
