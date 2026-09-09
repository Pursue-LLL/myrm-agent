"""SSH Host Asset Manager for storing, querying, and managing remote host assets.

[INPUT]
- SSHHostAsset, SSHConfigParsedHost, SSHAuthMethod from .models
- OpenSSHConfigParser from .parser

[OUTPUT]
- SSHAssetManager class

[POS]
Domain service in app/services/ssh_bridge/.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from app.services.ssh_bridge.models import (
    SSHAuthMethod,
    SSHHostAsset,
)
from app.services.ssh_bridge.parser import OpenSSHConfigParser


class SSHAssetManager:
    """In-memory encrypted registry and manager for multi-host SSH assets."""

    def __init__(self) -> None:
        self._assets_by_id: dict[str, SSHHostAsset] = {}
        self._alias_to_id: dict[str, str] = {}

    def register_asset(self, asset: SSHHostAsset) -> SSHHostAsset:
        """Register or update an SSH host asset. Enforces unique aliases."""
        alias_key = asset.alias.lower()
        if alias_key in self._alias_to_id and self._alias_to_id[alias_key] != asset.asset_id:
            msg = f"SSH host alias '{asset.alias}' is already registered to a different asset."
            raise ValueError(msg)

        self._assets_by_id[asset.asset_id] = asset
        self._alias_to_id[alias_key] = asset.asset_id
        return asset

    def get_by_alias(self, alias: str) -> SSHHostAsset | None:
        """Retrieve an active host asset by its unique alias."""
        asset_id = self._alias_to_id.get(alias.lower())
        if not asset_id:
            return None
        return self._assets_by_id.get(asset_id)

    def get_by_id(self, asset_id: str) -> SSHHostAsset | None:
        """Retrieve an asset by its primary ID."""
        return self._assets_by_id.get(asset_id)

    def list_assets(self, tag: str | None = None, active_only: bool = True) -> Sequence[SSHHostAsset]:
        """List registered assets, optionally filtering by tag or active state."""
        results: list[SSHHostAsset] = []
        for asset in self._assets_by_id.values():
            if active_only and not asset.is_active:
                continue
            if tag and tag not in asset.tags:
                continue
            results.append(asset)
        return tuple(results)

    def delete_asset(self, alias_or_id: str) -> bool:
        """Delete an asset by alias or asset_id."""
        target_id = alias_or_id
        if alias_or_id.lower() in self._alias_to_id:
            target_id = self._alias_to_id[alias_or_id.lower()]

        if target_id in self._assets_by_id:
            asset = self._assets_by_id.pop(target_id)
            self._alias_to_id.pop(asset.alias.lower(), None)
            return True
        return False

    def import_from_ssh_config(
        self,
        config_text: str,
        default_user: str = "root",
        tags: tuple[str, ...] = ("imported_config",),
    ) -> Sequence[SSHHostAsset]:
        """Import host sections from an OpenSSH configuration string into registered assets."""
        parsed_hosts = OpenSSHConfigParser.parse_text(config_text)
        imported: list[SSHHostAsset] = []

        for item in parsed_hosts:
            # Skip catch-all wildcard patterns
            if item.pattern in ("*", "*.*") or not item.host_name:
                continue

            alias = item.pattern.strip()
            # Determine auth method
            auth_method = SSHAuthMethod.KEY_FILE if item.identity_file else SSHAuthMethod.AGENT

            asset = SSHHostAsset(
                asset_id=f"ssh_asset_{uuid.uuid4().hex[:12]}",
                alias=alias,
                host_name=item.host_name,
                port=item.port,
                user=item.user or default_user,
                auth_method=auth_method,
                identity_file_path=item.identity_file,
                proxy_jump=item.proxy_jump,
                tags=tags,
                description=f"Imported from ~/.ssh/config host pattern '{item.pattern}'",
            )
            self.register_asset(asset)
            imported.append(asset)

        return tuple(imported)

    def import_from_config_text(
        self,
        config_text: str,
        default_user: str = "root",
        tags: tuple[str, ...] = ("imported_config",),
    ) -> int:
        """Convenience method returning the count of successfully imported assets."""
        imported = self.import_from_ssh_config(config_text, default_user=default_user, tags=tags)
        return len(imported)
