"""Host Asset Vault service for encrypted credential storage and SSH config import.

[INPUT]
- .models::HostAsset, HostAssetCreate, HostAssetUpdate, AuthType
- nacl / cryptography for secure credential encryption

[OUTPUT]
- HostAssetVault: Service managing host assets with encrypted secrets

[POS]
Domain service in app/services/host_assets/vault.py.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from pathlib import Path

from nacl.secret import SecretBox
from nacl.utils import random as nacl_random

from app.services.host_assets.models import (
    AuthType,
    HostAsset,
    HostAssetCreate,
)


class HostAssetVault:
    """Manages remote host assets with AES-GCM / XSalsa20 encrypted credentials."""

    def __init__(self, master_key: bytes | None = None) -> None:
        if master_key is None:
            # Derive or fetch master key from environment or fallback to dedicated entropy
            env_key = os.getenv("HOST_ASSET_VAULT_KEY")
            if env_key:
                try:
                    self._key = base64.urlsafe_b64decode(env_key.encode("ascii"))
                except Exception:
                    self._key = env_key.encode("utf-8").ljust(32, b"0")[:32]
            else:
                # Default 32-byte deterministic/local fallback key
                self._key = b"myrm-host-assets-secure-vault-32"
        else:
            self._key = master_key[:32].ljust(32, b"0")

        self._box = SecretBox(self._key)
        self._assets: dict[str, HostAsset] = {}
        self._alias_index: dict[str, str] = {}

    def _encrypt_payload(self, data: dict[str, str]) -> str:
        raw_json = json.dumps(data).encode("utf-8")
        nonce = nacl_random(SecretBox.NONCE_SIZE)
        encrypted = self._box.encrypt(raw_json, nonce)
        return base64.urlsafe_b64encode(encrypted).decode("ascii")

    def _decrypt_payload(self, encrypted_b64: str) -> dict[str, str]:
        if not encrypted_b64:
            return {}
        try:
            raw_encrypted = base64.urlsafe_b64decode(encrypted_b64.encode("ascii"))
            decrypted = self._box.decrypt(raw_encrypted)
            return json.loads(decrypted.decode("utf-8"))
        except Exception:
            return {}

    def create_asset(self, payload: HostAssetCreate) -> HostAsset:
        """Register and encrypt a new host asset."""
        if payload.alias in self._alias_index:
            raise ValueError(f"Host asset with alias '{payload.alias}' already exists.")

        asset_id = str(uuid.uuid4())
        now = time.time()

        secret_data: dict[str, str] = {}
        if payload.password:
            secret_data["password"] = payload.password
        if payload.private_key:
            secret_data["private_key"] = payload.private_key
        if payload.passphrase:
            secret_data["passphrase"] = payload.passphrase

        encrypted_secret = self._encrypt_payload(secret_data) if secret_data else ""

        asset = HostAsset(
            id=asset_id,
            alias=payload.alias,
            hostname=payload.hostname,
            port=payload.port,
            username=payload.username,
            auth_type=payload.auth_type,
            description=payload.description,
            has_password=bool(payload.password),
            has_private_key=bool(payload.private_key),
            encrypted_secret=encrypted_secret,
            created_at=now,
            updated_at=now,
        )

        self._assets[asset_id] = asset
        self._alias_index[payload.alias] = asset_id
        return asset

    def get_asset(self, host_id_or_alias: str) -> HostAsset | None:
        """Retrieve host asset metadata (without decrypting secrets)."""
        asset_id = self._alias_index.get(host_id_or_alias, host_id_or_alias)
        return self._assets.get(asset_id)

    def get_decrypted_secrets(self, host_id_or_alias: str) -> dict[str, str]:
        """Retrieve decrypted credentials for authorized internal execution gateway."""
        asset = self.get_asset(host_id_or_alias)
        if not asset or not asset.encrypted_secret:
            return {}
        return self._decrypt_payload(asset.encrypted_secret)

    def list_assets(self) -> list[HostAsset]:
        """List all registered host assets."""
        return list(self._assets.values())

    def delete_asset(self, host_id_or_alias: str) -> bool:
        """Delete a registered host asset."""
        asset = self.get_asset(host_id_or_alias)
        if not asset:
            return False
        self._assets.pop(asset.id, None)
        self._alias_index.pop(asset.alias, None)
        return True

    def import_from_ssh_config_content(self, config_text: str) -> list[HostAsset]:
        """Parse OpenSSH client config text and batch import host assets."""
        imported: list[HostAsset] = []
        current_host: dict[str, str] = {}

        lines = config_text.splitlines()
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) < 2:
                continue

            key, value = parts[0].lower(), parts[1]

            if key == "host":
                if current_host.get("alias") and current_host.get("hostname"):
                    imported.append(self._save_imported_host(current_host))
                # Skip wildcards like Host *
                if "*" in value or "?" in value:
                    current_host = {}
                else:
                    current_host = {"alias": value, "hostname": value}
            elif current_host:
                if key == "hostname":
                    current_host["hostname"] = value
                elif key == "user":
                    current_host["username"] = value
                elif key == "port":
                    current_host["port"] = value
                elif key == "identityfile":
                    current_host["identity_file"] = value

        if current_host.get("alias") and current_host.get("hostname"):
            imported.append(self._save_imported_host(current_host))

        return imported

    def _save_imported_host(self, data: dict[str, str]) -> HostAsset:
        alias = data.get("alias", "imported-host")
        # De-duplicate alias if exists
        original_alias = alias
        idx = 1
        while alias in self._alias_index:
            alias = f"{original_alias}-{idx}"
            idx += 1

        hostname = data.get("hostname", "127.0.0.1")
        port = int(data.get("port", 22))
        username = data.get("username", os.getenv("USER", "root"))
        id_file = data.get("identity_file")

        private_key = None
        if id_file:
            expanded_path = Path(os.path.expanduser(id_file))
            if expanded_path.is_file():
                try:
                    private_key = expanded_path.read_text(encoding="utf-8")
                except Exception:
                    private_key = None

        payload = HostAssetCreate(
            alias=alias,
            hostname=hostname,
            port=port,
            username=username,
            auth_type=AuthType.PRIVATE_KEY if private_key else AuthType.AGENT,
            description=f"Imported from SSH config (IdentityFile: {id_file or 'Default'})",
            private_key=private_key,
        )
        return self.create_asset(payload)
