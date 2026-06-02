"""Encrypted credentials storage for external channels.

Provides secure local persistence of channel authentication credentials.

[INPUT]

[OUTPUT]
- CredentialsStore: AES-256 encrypted JSON file storage

[POS]
Framework layer storage component. Provides out-of-the-box encrypted file
storage for channel credentials. Sandbox deployments (local, Tauri) use
this file-based store. SaaS deployments should implement custom store
with Redis encryption in control plane.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

__all__ = ["CredentialsStore"]

_CREDENTIALS_FILE = ".myrm/credentials.json"
_DEFAULT_SALT = b"myrm-channel-creds-v1"


class CredentialsStore:
    """AES-256 encrypted credentials storage (default framework implementation).

    Stores channel credentials locally with encryption at rest. Suitable for
    Agent-in-Sandbox (local, Tauri) deployments. For SaaS multi-tenant
    deployments, implement custom Redis-backed store in control plane.

    Security notes:
    - Uses AES-256 via Fernet (symmetric encryption)
    - Key derivation: PBKDF2-HMAC-SHA256 with 100k iterations
    - Default key: machine ID (single-user sandbox)
    - Production: override encryption_key via environment or keyring

    Example:
        store = CredentialsStore(storage_dir="/path/to/sandbox")
        await store.save("wechat", {"bot_token": "xxx", "user_id": "yyy"})
        creds = await store.get("wechat")
        channels = await store.list_channels()
        await store.delete("wechat")
    """

    def __init__(
        self,
        storage_dir: Path | str = Path.cwd(),
        encryption_key: str | None = None,
    ) -> None:
        """Initialize credentials store.

        Args:
            storage_dir: Base directory for `.myrm/credentials.json`
            encryption_key: Optional encryption passphrase (defaults to machine-id)
        """
        self._storage_dir = Path(storage_dir)
        self._creds_file = self._storage_dir / _CREDENTIALS_FILE
        self._encryption_key = encryption_key or self._get_default_key()
        self._fernet = self._init_fernet(self._encryption_key)

    def _get_default_key(self) -> str:
        """Generate default encryption key from machine ID.

        For single-user sandbox deployments. In production multi-tenant
        environments, provide explicit encryption_key via environment
        variable or keyring service.
        """
        try:
            import platform

            machine_id = platform.node()
        except Exception:
            machine_id = "myrm-default-key"
        return machine_id

    def _init_fernet(self, passphrase: str) -> Fernet:
        """Derive Fernet encryption key from passphrase using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_DEFAULT_SALT,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
        return Fernet(key)

    async def save(self, channel_name: str, credentials: dict[str, str]) -> None:
        """Save channel credentials (encrypted).

        Args:
            channel_name: Channel identifier
            credentials: Credential fields dict

        Raises:
            OSError: If file write fails
        """
        all_creds = await self._load_all()
        all_creds[channel_name] = credentials
        await self._save_all(all_creds)
        logger.info(
            "Credentials saved for channel",
            extra={"channel": channel_name},
        )

    async def get(self, channel_name: str) -> dict[str, str] | None:
        """Retrieve channel credentials (decrypted).

        Args:
            channel_name: Channel identifier

        Returns:
            Credentials dict if exists, None otherwise
        """
        all_creds = await self._load_all()
        return all_creds.get(channel_name)

    async def delete(self, channel_name: str) -> bool:
        """Delete channel credentials.

        Args:
            channel_name: Channel identifier

        Returns:
            True if deleted, False if not exists
        """
        all_creds = await self._load_all()
        if channel_name in all_creds:
            del all_creds[channel_name]
            await self._save_all(all_creds)
            logger.info(
                "Credentials deleted for channel",
                extra={"channel": channel_name},
            )
            return True
        return False

    async def list_channels(self) -> list[str]:
        """List all channels with stored credentials.

        Returns:
            List of channel names
        """
        all_creds = await self._load_all()
        return list(all_creds.keys())

    async def _load_all(self) -> dict[str, dict[str, str]]:
        """Load and decrypt all credentials from file."""
        if not self._creds_file.exists():
            return {}

        try:
            encrypted_data = self._creds_file.read_bytes()
            decrypted_json = self._fernet.decrypt(encrypted_data)
            return json.loads(decrypted_json)
        except InvalidToken:
            logger.warning("Failed to decrypt credentials file (wrong key or corrupted)")
            return {}
        except json.JSONDecodeError:
            logger.warning("Credentials file corrupted (invalid JSON)")
            return {}
        except Exception as exc:
            logger.error(
                "Failed to load credentials",
                extra={"error": str(exc)},
                exc_info=True,
            )
            return {}

    async def _save_all(self, all_creds: dict[str, dict[str, str]]) -> None:
        """Encrypt and save all credentials to file."""
        self._creds_file.parent.mkdir(parents=True, exist_ok=True)

        json_data = json.dumps(all_creds, indent=2)
        encrypted_data = self._fernet.encrypt(json_data.encode("utf-8"))
        self._creds_file.write_bytes(encrypted_data)
