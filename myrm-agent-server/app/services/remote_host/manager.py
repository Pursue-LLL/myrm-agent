"""Remote Host Asset Management Service.

Provides discovery, storage, and retrieval of SSH host configurations,
including parsing from standard ~/.ssh/config files.

[INPUT]
- .models::RemoteHostConfig, RemoteHostSummary, HostAssetImportResult
- pathlib::Path
- typing::Dict, List, Optional
- re, os, logging

[OUTPUT]
- RemoteHostManager: Service for managing remote host assets.

[POS]
Domain service in app/services/remote_host/.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from app.services.remote_host.models import (
    HostAssetImportResult,
    RemoteHostConfig,
    RemoteHostSummary,
)

logger = logging.getLogger("myrm.services.remote_host.manager")


class RemoteHostManager:
    """In-memory and file-backed SSH host asset manager."""

    def __init__(self) -> None:
        self._hosts: Dict[str, RemoteHostConfig] = {}

    def register_host(self, host: RemoteHostConfig) -> RemoteHostConfig:
        """Add or update a host asset."""
        self._hosts[host.alias] = host
        logger.info("Registered remote host asset: alias=%s, host=%s", host.alias, host.hostname)
        return host

    def get_host(self, alias: str) -> Optional[RemoteHostConfig]:
        """Retrieve a registered host configuration by alias."""
        return self._hosts.get(alias)

    def remove_host(self, alias: str) -> bool:
        """Remove a host asset by alias."""
        if alias in self._hosts:
            del self._hosts[alias]
            logger.info("Removed remote host asset: alias=%s", alias)
            return True
        return False

    def list_hosts(self, active_only: bool = True) -> List[RemoteHostSummary]:
        """List sanitized summaries of registered hosts."""
        summaries: List[RemoteHostSummary] = []
        for h in self._hosts.values():
            if active_only and not h.is_active:
                continue
            summaries.append(
                RemoteHostSummary(
                    alias=h.alias,
                    hostname=h.hostname,
                    port=h.port,
                    username=h.username,
                    auth_type=h.auth_type,
                    tags=h.tags,
                    is_active=h.is_active,
                )
            )
        return summaries

    def import_from_ssh_config(
        self,
        config_path: Optional[str] = None,
        overwrite: bool = False,
    ) -> HostAssetImportResult:
        """Parse standard ~/.ssh/config and import host blocks as assets."""
        path = Path(config_path or os.path.expanduser("~/.ssh/config"))
        if not path.exists() or not path.is_file():
            return HostAssetImportResult(
                total_discovered=0,
                imported=[],
                skipped=[],
                errors=[f"SSH config file not found at {path}"],
            )

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return HostAssetImportResult(
                total_discovered=0,
                imported=[],
                skipped=[],
                errors=[f"Failed to read SSH config: {e}"],
            )

        imported: List[str] = []
        skipped: List[str] = []
        errors: List[str] = []

        # Parse Host blocks
        current_host: Optional[str] = None
        props: Dict[str, str] = {}

        for line in content.splitlines():
            line_clean = line.strip()
            if not line_clean or line_clean.startswith("#"):
                continue

            parts = line_clean.split(None, 1)
            if len(parts) < 2:
                continue

            key = parts[0].lower()
            val = parts[1].strip()

            if key == "host":
                # Save previous host block
                if current_host and current_host != "*" and "hostname" in props:
                    self._save_parsed_host(current_host, props, overwrite, imported, skipped)
                current_host = val
                props = {}
            elif current_host and current_host != "*":
                props[key] = val

        # Save final host block
        if current_host and current_host != "*" and "hostname" in props:
            self._save_parsed_host(current_host, props, overwrite, imported, skipped)

        return HostAssetImportResult(
            total_discovered=len(imported) + len(skipped),
            imported=imported,
            skipped=skipped,
            errors=errors,
        )

    def _save_parsed_host(
        self,
        alias: str,
        props: Dict[str, str],
        overwrite: bool,
        imported: List[str],
        skipped: List[str],
    ) -> None:
        if alias in self._hosts and not overwrite:
            skipped.append(alias)
            return

        hostname = props.get("hostname", alias)
        port = int(props.get("port", "22"))
        user = props.get("user", "root")
        identity = props.get("identityfile")

        config = RemoteHostConfig(
            alias=alias,
            hostname=hostname,
            port=port,
            username=user,
            auth_type="key" if identity else "agent",
            identity_file=os.path.expanduser(identity) if identity else None,
            description=f"Auto-imported from ~/.ssh/config (Host {alias})",
            tags=["ssh-config"],
        )
        self.register_host(config)
        imported.append(alias)
