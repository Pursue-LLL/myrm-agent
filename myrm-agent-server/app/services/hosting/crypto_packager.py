"""Crypto packaging utilities for secure static artifact publishing.

[POS] Encrypts multi-file static artifacts into an in-memory VFS encrypted bundle
wrapped with a zero-dependency Web Crypto AES-256-GCM HTML bootstrap shell.

[INPUT]
- dict[str, PublishFile]: Raw static files for the artifact
- str: User provided password
- app.services.hosting.decryptor_shell::render_decryptor_shell (POS: the page every visitor of an encrypted publish opens: a lock card plus the in-browser decrypt-and-mount script)

[OUTPUT]
- dict[str, PublishFile]: Single index.html containing encrypted payload + decryptor shell
"""

from __future__ import annotations

import base64
import json
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.services.hosting.decryptor_shell import render_decryptor_shell
from app.services.hosting.packager import PublishFile

# OWASP's PBKDF2-HMAC-SHA256 floor. The ciphertext is publicly hosted, so offline guessing is the threat; each payload
# carries its own count, so pages published with a lower one still open.
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16
NONCE_BYTES = 12


def _derive_aes_key(password: str, salt: bytes) -> bytes:
    """Derive 256-bit AES-GCM key from password and salt via PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _encrypt_payload(payload_bytes: bytes, password: str) -> dict[str, str]:
    """Encrypt byte payload with AES-256-GCM using a PBKDF2-derived key."""
    salt = secrets.token_bytes(SALT_BYTES)
    nonce = secrets.token_bytes(NONCE_BYTES)
    key = _derive_aes_key(password, salt)

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, payload_bytes, None)

    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "iterations": str(PBKDF2_ITERATIONS),
    }


def _decrypt_payload(encrypted_dict: dict[str, str], password: str) -> bytes:
    """Decrypt byte payload from encrypted dict (used for self-verification tests)."""
    salt = base64.b64decode(encrypted_dict["salt"])
    nonce = base64.b64decode(encrypted_dict["nonce"])
    ciphertext = base64.b64decode(encrypted_dict["ciphertext"])
    iterations = int(encrypted_dict["iterations"])

    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    key = kdf.derive(password.encode("utf-8"))
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def package_encrypted_publish_files(
    files: dict[str, PublishFile],
    password: str,
    *,
    title: str = "Protected Artifact",
) -> dict[str, PublishFile]:
    """Package multi-file artifact into a single encrypted deployable index.html payload."""
    if not password:
        return files

    vfs_dict: dict[str, dict[str, str]] = {}
    for entry_name, pfile in files.items():
        vfs_dict[entry_name] = {
            "content": pfile.content,
            "encoding": pfile.encoding,
        }

    raw_json_bytes = json.dumps(vfs_dict, ensure_ascii=False).encode("utf-8")
    encrypted_dict = _encrypt_payload(raw_json_bytes, password)
    shell_html = render_decryptor_shell(encrypted_dict, title=title)

    return {
        "index.html": PublishFile(
            path="index.html",
            content=shell_html,
            encoding="utf-8",
        )
    }
