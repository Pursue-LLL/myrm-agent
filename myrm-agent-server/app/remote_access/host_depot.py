"""Encrypted SSH Host Asset Depot for remote server credentials management.

[INPUT]
- app.config.settings::settings
- myrm_agent_harness.toolkits.ssh_remote.models::SSHHostSpec, SSHAuthType

[OUTPUT]
- HostAssetDepot, EncryptedHostRecord

[POS]
Core asset storage layer in app/remote_access/host_depot.py.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from myrm_agent_harness.toolkits.ssh_remote.models import SSHAuthType, SSHHostSpec

from app.config.settings import settings

logger = logging.getLogger(__name__)

_HOSTS_DIR = Path("remote_ops")
_DEPOT_FILE = "ssh_hosts.json"
_KEY_FILE = "host_depot_key"


@dataclass
class EncryptedHostRecord:
    """Persistent representation of an encrypted SSH host."""

    host_id: str
    hostname: str
    port: int = 22
    username: str = "root"
    auth_type: str = "password"
    encrypted_secret: str = ""  # Fernet-encrypted password or private_key
    passphrase_encrypted: str = ""
    proxy_jump: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    description: str = ""


class HostAssetDepot:
    """Manages secure persistent storage of SSH host credentials."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._dir = base_dir or (Path(settings.database.state_dir) / _HOSTS_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cipher = self._init_cipher()

    def _init_cipher(self) -> Fernet:
        key_path = self._dir / _KEY_FILE
        if key_path.is_file():
            key = key_path.read_bytes().strip()
            if len(key) == 44:  # Valid Fernet key length
                return Fernet(key)
        new_key = Fernet.generate_key()
        key_path.write_bytes(new_key)
        try:
            key_path.chmod(0o600)
        except OSError:
            pass
        return Fernet(new_key)

    def _get_store_path(self) -> Path:
        return self._dir / _DEPOT_FILE

    def _encrypt(self, text: Optional[str]) -> str:
        if not text:
            return ""
        return self._cipher.encrypt(text.encode("utf-8")).decode("ascii")

    def _decrypt(self, token: str) -> str:
        if not token:
            return ""
        try:
            return self._cipher.decrypt(token.encode("ascii")).decode("utf-8")
        except Exception as err:
            logger.error("Failed to decrypt host secret: %s", err)
            return ""

    def list_hosts(self) -> list[EncryptedHostRecord]:
        """List all stored host records."""
        path = self._get_store_path()
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [EncryptedHostRecord(**item) for item in data]
        except Exception as err:
            logger.error("Failed to load ssh hosts: %s", err)
            return []

    def get_host_spec(self, host_id: str) -> Optional[SSHHostSpec]:
        """Retrieve decrypted SSHHostSpec for Agent or proxy connection."""
        hosts = self.list_hosts()
        for rec in hosts:
            if rec.host_id == host_id:
                secret = self._decrypt(rec.encrypted_secret)
                passphrase = self._decrypt(rec.passphrase_encrypted)
                auth_enum = SSHAuthType(rec.auth_type)

                return SSHHostSpec(
                    host_id=rec.host_id,
                    hostname=rec.hostname,
                    port=rec.port,
                    username=rec.username,
                    auth_type=auth_enum,
                    password=secret if auth_enum == SSHAuthType.PASSWORD else None,
                    private_key=secret if auth_enum == SSHAuthType.PRIVATE_KEY else None,
                    passphrase=passphrase if passphrase else None,
                    proxy_jump=rec.proxy_jump,
                    tags=rec.tags,
                    description=rec.description,
                )
        return None

    def save_host(
        self,
        host_id: str,
        hostname: str,
        port: int = 22,
        username: str = "root",
        auth_type: SSHAuthType = SSHAuthType.PASSWORD,
        secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        proxy_jump: Optional[str] = None,
        tags: Optional[list[str]] = None,
        description: str = "",
    ) -> EncryptedHostRecord:
        """Create or update a host record."""
        hosts = self.list_hosts()
        encrypted_secret = self._encrypt(secret)
        passphrase_encrypted = self._encrypt(passphrase)

        new_rec = EncryptedHostRecord(
            host_id=host_id,
            hostname=hostname,
            port=port,
            username=username,
            auth_type=auth_type.value,
            encrypted_secret=encrypted_secret,
            passphrase_encrypted=passphrase_encrypted,
            proxy_jump=proxy_jump,
            tags=tags or [],
            description=description,
        )

        filtered = [h for h in hosts if h.host_id != host_id]
        filtered.append(new_rec)

        path = self._get_store_path()
        path.write_text(json.dumps([asdict(h) for h in filtered], indent=2), encoding="utf-8")
        return new_rec

    def delete_host(self, host_id: str) -> bool:
        """Remove a host record."""
        hosts = self.list_hosts()
        filtered = [h for h in hosts if h.host_id != host_id]
        if len(filtered) == len(hosts):
            return False
        path = self._get_store_path()
        path.write_text(json.dumps([asdict(h) for h in filtered], indent=2), encoding="utf-8")
        return True

    def import_from_ssh_config(self, config_text: str) -> list[EncryptedHostRecord]:
        """Parse SSH config text and import host stubs."""
        imported: list[EncryptedHostRecord] = []
        current_host: dict[str, str] = {}

        for line in config_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) != 2:
                continue

            key, val = parts[0].lower(), parts[1]
            if key == "host":
                if "host" in current_host and current_host["host"] != "*":
                    rec = self._create_record_from_config(current_host)
                    if rec:
                        imported.append(rec)
                current_host = {"host": val}
            else:
                current_host[key] = val

        if "host" in current_host and current_host["host"] != "*":
            rec = self._create_record_from_config(current_host)
            if rec:
                imported.append(rec)

        return imported

    def _create_record_from_config(self, config: dict[str, str]) -> Optional[EncryptedHostRecord]:
        host_id = config.get("host", "").strip()
        hostname = config.get("hostname", host_id).strip()
        if not host_id or not hostname:
            return None

        port = int(config.get("port", "22"))
        username = config.get("user", "root")
        identity_file = config.get("identityfile")
        proxy_jump = config.get("proxyjump")

        auth_type = SSHAuthType.PRIVATE_KEY if identity_file else SSHAuthType.NONE
        secret: Optional[str] = None
        if identity_file:
            path = Path(os.path.expanduser(identity_file))
            if path.is_file():
                try:
                    secret = path.read_text(encoding="utf-8")
                except OSError:
                    pass

        return self.save_host(
            host_id=host_id,
            hostname=hostname,
            port=port,
            username=username,
            auth_type=auth_type,
            secret=secret,
            proxy_jump=proxy_jump,
            description=f"Imported from SSH config ({hostname})",
        )
