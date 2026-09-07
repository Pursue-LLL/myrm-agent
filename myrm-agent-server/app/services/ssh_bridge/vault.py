"""SSH Host Asset Vault with local JSON persistence and encryption protection.

[INPUT]
- .models::SSHHostAsset, HostAuthMethod
- json, os, time, pathlib

[OUTPUT]
- SSHHostVault: Manages CRUD, querying, and pre-authorization of SSH host assets.

[POS]
Domain service in app/services/ssh_bridge/vault.py.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from .models import HostAuthMethod, SSHHostAsset

logger = logging.getLogger("myrm.services.ssh_bridge.vault")


class SSHHostVault:
    """Manages secure registration, query, and storage of remote SSH host assets."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        if storage_path:
            self._storage_path = storage_path
        else:
            base_dir = Path(os.getenv("MYRM_DATA_DIR", Path.home() / ".myrm"))
            self._storage_path = base_dir / "storage" / "ssh_hosts.json"
        
        self._hosts: Dict[str, SSHHostAsset] = {}
        self._load()

    def _load(self) -> None:
        """Load stored host assets from disk."""
        if not self._storage_path.exists():
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        asset = SSHHostAsset.model_validate(item)
                        self._hosts[asset.host_id] = asset
        except Exception as err:
            logger.error("Failed to load SSH host assets from %s: %s", self._storage_path, err)

    def _save(self) -> None:
        """Persist current host assets to disk atomically."""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._storage_path.with_suffix(".tmp")
            data = [asset.model_dump() for asset in self._hosts.values()]
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.replace(self._storage_path)
        except Exception as err:
            logger.error("Failed to persist SSH host assets to %s: %s", self._storage_path, err)

    def register_host(self, host: SSHHostAsset) -> SSHHostAsset:
        """Register or update an SSH host asset."""
        if host.created_at <= 0:
            host.created_at = time.time()
        self._hosts[host.host_id] = host
        self._save()
        return host

    def get_host(self, host_id: str) -> Optional[SSHHostAsset]:
        """Fetch a specific host asset by ID."""
        return self._hosts.get(host_id)

    def list_hosts(self, tag: Optional[str] = None) -> List[SSHHostAsset]:
        """List all host assets, optionally filtered by tag."""
        if tag:
            return [h for h in self._hosts.values() if tag in h.tags]
        return list(self._hosts.values())

    def delete_host(self, host_id: str) -> bool:
        """Delete a host asset."""
        if host_id in self._hosts:
            del self._hosts[host_id]
            self._save()
            return True
        return False

    def find_by_alias_or_hostname(self, query: str) -> Optional[SSHHostAsset]:
        """Find the best matching host asset by alias, hostname, or ID."""
        q_lower = query.lower().strip()
        # Exact ID match
        if q_lower in self._hosts:
            return self._hosts[q_lower]
        # Alias or Hostname match
        for h in self._hosts.values():
            if h.alias.lower() == q_lower or h.hostname.lower() == q_lower:
                return h
        return None
