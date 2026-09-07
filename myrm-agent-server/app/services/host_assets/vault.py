"""Host asset vault and ~/.ssh/config parser implementation.

[INPUT]
- pathlib.Path, typing.Dict, typing.List, typing.Optional
- .models::HostAssetConfig, HostAuthType, HostConfigImportResult

[OUTPUT]
- HostAssetVault, parse_ssh_config_text

[POS]
Domain service in app/services/host_assets/ managing host assets and SSH configurations.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from app.services.host_assets.models import (
    HostAssetConfig,
    HostAuthType,
    HostConfigImportResult,
)


def parse_ssh_config_text(config_text: str) -> List[HostAssetConfig]:
    """Parse ~/.ssh/config content into a list of HostAssetConfig instances.

    Supports Host, HostName, User, Port, IdentityFile directives.
    """
    hosts: List[HostAssetConfig] = []
    lines = config_text.splitlines()

    current_host_alias: Optional[str] = None
    current_hostname: Optional[str] = None
    current_user: str = "root"
    current_port: int = 22
    current_identity_file: Optional[str] = None

    def flush_current() -> None:
        nonlocal current_host_alias, current_hostname, current_user, current_port, current_identity_file
        if current_host_alias and current_host_alias != "*":
            target_host = current_hostname or current_host_alias
            host_id = f"host_{current_host_alias.lower().replace('.', '_').replace('-', '_')}"
            auth_type = (
                HostAuthType.PRIVATE_KEY
                if current_identity_file
                else HostAuthType.PASSWORD
            )
            hosts.append(
                HostAssetConfig(
                    host_id=host_id,
                    name=current_host_alias,
                    hostname=target_host,
                    port=current_port,
                    username=current_user,
                    auth_type=auth_type,
                    private_key_path=current_identity_file,
                    description=f"Imported from ssh_config (Alias: {current_host_alias})",
                    tags=["ssh_config_import"],
                )
            )
        current_host_alias = None
        current_hostname = None
        current_user = "root"
        current_port = 22
        current_identity_file = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 1)
        if len(parts) < 2:
            continue

        key, val = parts[0].lower(), parts[1].strip()

        if key == "host":
            flush_current()
            current_host_alias = val
        elif key == "hostname":
            current_hostname = val
        elif key == "user":
            current_user = val
        elif key == "port":
            try:
                current_port = int(val)
            except ValueError:
                current_port = 22
        elif key in ("identityfile", "identity_file"):
            expanded = os.path.expanduser(val.strip('"'))
            current_identity_file = expanded

    flush_current()
    return hosts


class HostAssetVault:
    """In-memory and persisted storage for managed remote host assets."""

    def __init__(self) -> None:
        self._assets: Dict[str, HostAssetConfig] = {}

    def register_host(self, host: HostAssetConfig) -> HostAssetConfig:
        """Register or update a host asset configuration."""
        self._assets[host.host_id] = host
        return host

    def get_host(self, host_id: str) -> Optional[HostAssetConfig]:
        """Retrieve a host asset by ID."""
        return self._assets.get(host_id)

    def list_hosts(self, tag: Optional[str] = None) -> List[HostAssetConfig]:
        """List all registered hosts, optionally filtered by tag."""
        if tag is None:
            return list(self._assets.values())
        return [h for h in self._assets.values() if tag in h.tags]

    def remove_host(self, host_id: str) -> bool:
        """Remove a host asset by ID. Returns True if removed, False if not found."""
        if host_id in self._assets:
            del self._assets[host_id]
            return True
        return False

    def import_from_ssh_config(
        self,
        config_text: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> HostConfigImportResult:
        """Import hosts from a raw string or from ~/.ssh/config file path."""
        text = config_text
        errors: List[str] = []

        if text is None:
            path = Path(config_path or os.path.expanduser("~/.ssh/config"))
            if not path.exists():
                return HostConfigImportResult(
                    total_parsed=0,
                    total_imported=0,
                    imported_host_ids=[],
                    errors=[f"Config file not found at {path}"],
                )
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                return HostConfigImportResult(
                    total_parsed=0,
                    total_imported=0,
                    imported_host_ids=[],
                    errors=[f"Failed reading config file: {exc}"],
                )

        parsed_hosts = parse_ssh_config_text(text)
        imported_ids: List[str] = []

        for host in parsed_hosts:
            self.register_host(host)
            imported_ids.append(host.host_id)

        return HostConfigImportResult(
            total_parsed=len(parsed_hosts),
            total_imported=len(imported_ids),
            imported_host_ids=imported_ids,
            errors=errors,
        )
