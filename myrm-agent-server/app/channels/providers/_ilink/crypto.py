"""AES-128-ECB encryption/decryption for WeChat iLink media.

WeChat iLink uses AES-128-ECB for encrypting media files uploaded to/from CDN.

[INPUT]
- cryptography.hazmat.primitives.ciphers::Cipher, algorithms, modes

[OUTPUT]
- encrypt_media, decrypt_media, generate_aes_key
- download_and_decrypt, encrypt_and_upload

[POS]
WeChat iLink media encryption utility. Uses AES-128-ECB mode (per WeChat CDN requirements).
"""

from __future__ import annotations

import base64
import logging
import secrets
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = 30.0
_UPLOAD_TIMEOUT_SMALL = 60.0
_UPLOAD_TIMEOUT_LARGE = 180.0
_LARGE_FILE_THRESHOLD = 10 * 1024 * 1024
_MAX_FILE_SIZE_MB = 100


def generate_aes_key() -> str:
    """Generate a random 16-byte AES key, returned as base64 string."""
    return base64.b64encode(secrets.token_bytes(16)).decode()


def encrypt_media(plaintext: bytes, aes_key_b64: str) -> bytes:
    """Encrypt media bytes with AES-128-ECB + PKCS7 padding."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = base64.b64decode(aes_key_b64)
    if len(key) != 16:
        raise ValueError(f"AES key must be 16 bytes, got {len(key)}")

    padded = _pkcs7_pad(plaintext, 16)
    cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def decrypt_media(ciphertext: bytes, aes_key_b64: str) -> bytes:
    """Decrypt media bytes with AES-128-ECB, remove PKCS7 padding."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = base64.b64decode(aes_key_b64)
    if len(key) != 16:
        raise ValueError(f"AES key must be 16 bytes, got {len(key)}")

    cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    return _pkcs7_unpad(padded)


def _pkcs7_pad(data: bytes, block_size: int) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("Cannot unpad empty data")
    pad_len = data[-1]
    if pad_len > len(data) or pad_len == 0:
        raise ValueError("Invalid PKCS7 padding")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("Invalid PKCS7 padding bytes")
    return data[:-pad_len]


async def download_and_decrypt(
    url: str,
    aes_key_b64: str,
    output_path: Path,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    """Download encrypted media from CDN and decrypt to local file."""
    if http_client:
        resp = await http_client.get(url, timeout=_DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        ciphertext = resp.content
    else:
        async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ciphertext = resp.content

    plaintext = decrypt_media(ciphertext, aes_key_b64)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(plaintext)


async def encrypt_and_upload(
    file_path: Path,
    upload_url: str,
    aes_key_b64: str,
    http_client: httpx.AsyncClient | None = None,
) -> int:
    """Encrypt local file and upload to WeChat CDN.

    Returns encrypted file size in bytes.
    """
    file_size = file_path.stat().st_size
    max_bytes = _MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size > max_bytes:
        raise ValueError(f"File size {file_size / 1024 / 1024:.1f}MB exceeds maximum {_MAX_FILE_SIZE_MB}MB")

    timeout = _UPLOAD_TIMEOUT_SMALL if file_size < _LARGE_FILE_THRESHOLD else _UPLOAD_TIMEOUT_LARGE

    plaintext = file_path.read_bytes()
    ciphertext = encrypt_media(plaintext, aes_key_b64)

    if http_client:
        resp = await http_client.post(
            upload_url,
            content=ciphertext,
            headers={"Content-Type": "application/octet-stream"},
            timeout=timeout,
        )
        resp.raise_for_status()
    else:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                upload_url,
                content=ciphertext,
                headers={"Content-Type": "application/octet-stream"},
            )
            resp.raise_for_status()

    return len(ciphertext)
