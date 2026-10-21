"""Persistent daemon X25519 keypair for remote-access E2EE.

[INPUT]
- MYRM_DATA_DIR / filesystem path for key persistence

[OUTPUT]
- get_or_create_keypair(): X25519 keypair (public + secret)

[POS]
Key management. Generates and persists the daemon's E2EE identity keypair.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import settings
from app.remote_access.e2ee.crypto import generate_keypair, public_key_b64, public_key_from_b64

logger = logging.getLogger(__name__)

_KEY_VERSION = 1
_KEY_FILE = Path("webui") / "e2ee_daemon_keypair.json"


@dataclass(frozen=True, slots=True)
class DaemonKeypair:
    public_key: bytes
    secret_key: bytes

    @property
    def public_key_b64(self) -> str:
        return public_key_b64(self.public_key)


def _key_path() -> Path:
    return Path(settings.database.state_dir) / _KEY_FILE


def load_or_create_daemon_keypair() -> DaemonKeypair:
    path = _key_path()
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            pub = payload.get("publicKeyB64")
            sec = payload.get("secretKeyB64")
            if isinstance(pub, str) and isinstance(sec, str):
                public_key = public_key_from_b64(pub)
                padded = sec + "=" * (-len(sec) % 4)
                secret_key = base64.urlsafe_b64decode(padded.encode("ascii"))
                if len(secret_key) == 32:
                    return DaemonKeypair(public_key=public_key, secret_key=secret_key)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Regenerating unreadable E2EE daemon keypair: %s", exc)

    public_key, secret_key = generate_keypair()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "v": _KEY_VERSION,
        "publicKeyB64": public_key_b64(public_key),
        "secretKeyB64": base64.urlsafe_b64encode(secret_key).decode("ascii").rstrip("="),
    }
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    path.chmod(0o600)
    logger.info("Created E2EE daemon keypair at %s", path)
    return DaemonKeypair(public_key=public_key, secret_key=secret_key)


__all__ = ["DaemonKeypair", "load_or_create_daemon_keypair"]
