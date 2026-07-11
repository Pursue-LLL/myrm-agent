"""VAPID key management — generate, persist, and load ECDSA P-256 key pairs.

Keys are stored as PEM files under ``state_dir/web_push/``. Generated lazily
on first access if missing. Thread-safe via ``filelock``.

[INPUT]
- app.config.settings::settings.database.state_dir

[OUTPUT]
- load_vapid_keys(): returns (private_pem, public_key_urlsafe_b64) tuple
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from filelock import FileLock

logger = logging.getLogger(__name__)

_VAPID_DIR_NAME = "web_push"
_PRIVATE_KEY_FILE = "vapid_private_key.pem"
_PUBLIC_KEY_FILE = "vapid_public_key.txt"


def _get_vapid_dir() -> Path:
    from app.config.settings import settings

    vapid_dir = Path(settings.database.state_dir) / _VAPID_DIR_NAME
    vapid_dir.mkdir(parents=True, exist_ok=True)
    return vapid_dir


def _generate_keys(vapid_dir: Path) -> tuple[str, str]:
    """Generate a new ECDSA P-256 key pair and persist to disk."""
    private_key = ec.generate_private_key(ec.SECP256R1())

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = base64.urlsafe_b64encode(public_bytes).decode("ascii").rstrip("=")

    private_pem = private_pem.strip()
    priv_path = vapid_dir / _PRIVATE_KEY_FILE
    priv_path.write_text(private_pem)
    os.chmod(priv_path, 0o600)
    pub_path = vapid_dir / _PUBLIC_KEY_FILE
    pub_path.write_text(public_b64)
    os.chmod(pub_path, 0o644)
    logger.info("VAPID key pair generated at %s", vapid_dir)
    return private_pem, public_b64


def load_vapid_keys() -> tuple[str, str]:
    """Load or generate VAPID key pair.

    Returns:
        (private_pem_str, application_server_key_urlsafe_b64)
    """
    vapid_dir = _get_vapid_dir()
    lock_path = vapid_dir / ".vapid.lock"

    with FileLock(str(lock_path)):
        priv_path = vapid_dir / _PRIVATE_KEY_FILE
        pub_path = vapid_dir / _PUBLIC_KEY_FILE

        if priv_path.exists() and pub_path.exists():
            return priv_path.read_text().strip(), pub_path.read_text().strip()

        return _generate_keys(vapid_dir)
