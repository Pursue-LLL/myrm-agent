"""Passphrase envelope for the config encryption key.

[INPUT]
- hashlib.scrypt: passphrase → wrapping key
- myrm_agent_harness.utils.crypto::ConfigCrypto (POS: AES-256-GCM value encryption)

[OUTPUT]
- seal_key / unseal_key: wrap and unwrap the 32-byte config encryption key
- EnvelopeError: wrong passphrase, malformed or out-of-policy envelope
- MIN_PASSPHRASE_LENGTH

[POS]
Lets sensitive user_configs rows travel as their original ciphertext: only the
single key that encrypts them is wrapped, so the archive never contains a
plaintext secret and ``.encryption_key`` itself is never archived. KDF
parameters are read from the (untrusted) archive, hence bounded before use.
"""

from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Mapping

from myrm_agent_harness.utils.crypto import ConfigCrypto, DecryptionError

ENVELOPE_VERSION = 1
MIN_PASSPHRASE_LENGTH = 8

_SCRYPT_N = 2**17  # OWASP-recommended work factor: N=2^17, r=8, p=1
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_MAX_N, _MAX_R, _MAX_P = 2**20, 16, 4
_KEY_BYTES = 32


class EnvelopeError(ValueError):
    """The envelope cannot be opened with the given passphrase."""


def _wrapping_key(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    maxmem = 256 * n * r + 16 * 1024 * 1024  # scrypt needs ~128*n*r bytes; keep headroom
    return hashlib.scrypt(passphrase.encode(), salt=salt, n=n, r=r, p=p, maxmem=maxmem, dklen=_KEY_BYTES)


def seal_key(key: bytes, passphrase: str) -> dict[str, object]:
    salt = os.urandom(_SALT_BYTES)
    wrapping = _wrapping_key(passphrase, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    sealed = ConfigCrypto.encrypt_value({"key": base64.b64encode(key).decode("ascii")}, wrapping)
    return {
        "version": ENVELOPE_VERSION,
        "kdf": "scrypt",
        "n": _SCRYPT_N,
        "r": _SCRYPT_R,
        "p": _SCRYPT_P,
        "salt": base64.b64encode(salt).decode("ascii"),
        "sealed": sealed,
    }


def _int_param(envelope: Mapping[str, object], name: str, upper: int) -> int:
    value = envelope.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= upper:
        raise EnvelopeError(f"Envelope parameter '{name}' is out of range")
    return value


def unseal_key(envelope: Mapping[str, object], passphrase: str) -> bytes:
    if envelope.get("version") != ENVELOPE_VERSION or envelope.get("kdf") != "scrypt":
        raise EnvelopeError("Unsupported envelope format")
    n = _int_param(envelope, "n", _MAX_N)
    if n & (n - 1):
        raise EnvelopeError("Envelope parameter 'n' must be a power of two")
    r = _int_param(envelope, "r", _MAX_R)
    p = _int_param(envelope, "p", _MAX_P)
    salt_b64, sealed = envelope.get("salt"), envelope.get("sealed")
    if not isinstance(salt_b64, str) or not isinstance(sealed, str):
        raise EnvelopeError("Envelope is malformed")
    try:
        wrapping = _wrapping_key(passphrase, base64.b64decode(salt_b64, validate=True), n, r, p)
        payload = ConfigCrypto.decrypt_value(sealed, wrapping)
        key = base64.b64decode(str(payload["key"]), validate=True)
    except (DecryptionError, KeyError, ValueError) as exc:
        raise EnvelopeError("Wrong passphrase or corrupted envelope") from exc
    if len(key) != _KEY_BYTES:
        raise EnvelopeError("Envelope key has an unexpected length")
    return key
