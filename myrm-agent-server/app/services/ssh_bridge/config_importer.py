"""SSH Config Importer: parses standard ~/.ssh/config files into structured SSHHostAsset items.

[INPUT]
- .models::SSHHostAsset, HostAuthMethod
- pathlib, re, os

[OUTPUT]
- SSHConfigImporter: Parses SSH config text or file into List[SSHHostAsset].

[POS]
Domain service in app/services/ssh_bridge/config_importer.py.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from .models import HostAuthMethod, SSHHostAsset

logger = logging.getLogger("myrm.services.ssh_bridge.config_importer")


class SSHConfigImporter:
    """Parses OpenSSH client configuration format (~/.ssh/config)."""

    @classmethod
    def parse_config_file(cls, config_path: Optional[Path] = None) -> List[SSHHostAsset]:
        """Parse default or provided ~/.ssh/config file."""
        target = config_path or (Path.home() / ".ssh" / "config")
        if not target.exists():
            logger.info("SSH config file %s not found", target)
            return []
        try:
            with open(target, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return cls.parse_config_text(content)
        except Exception as err:
            logger.error("Failed to read SSH config from %s: %s", target, err)
            return []

    @classmethod
    def parse_config_text(cls, text: str) -> List[SSHHostAsset]:
        """Parse raw text from an ssh config file."""
        hosts: List[SSHHostAsset] = []
        current_entry: Dict[str, str] = {}
        current_alias: Optional[str] = None

        lines = text.splitlines()

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Check for Host entry
            match_host = re.match(r"^Host\s+(.+)$", stripped, re.IGNORECASE)
            if match_host:
                alias = match_host.group(1).strip()
                # Wildcards like '*' are ignored as concrete host targets
                if "*" in alias or "?" in alias:
                    current_alias = None
                    current_entry = {}
                    continue

                # Save previous entry if valid
                if current_alias and "hostname" in current_entry:
                    cls._append_parsed_asset(hosts, current_alias, current_entry)

                current_alias = alias
                current_entry = {}
                continue

            if not current_alias:
                continue

            # Parse key-value directives
            parts = re.split(r"[\s=]+", stripped, maxsplit=1)
            if len(parts) == 2:
                key = parts[0].lower()
                val = parts[1].strip("\"' ")
                current_entry[key] = val

        # Append last pending entry
        if current_alias and "hostname" in current_entry:
            cls._append_parsed_asset(hosts, current_alias, current_entry)

        return hosts

    @staticmethod
    def _append_parsed_asset(
        target_list: List[SSHHostAsset],
        alias: str,
        entry: Dict[str, str],
    ) -> None:
        """Construct SSHHostAsset and append to target list."""
        hostname = entry.get("hostname", alias)
        user = entry.get("user", os.getenv("USER", "root"))
        port_raw = entry.get("port", "22")
        try:
            port = int(port_raw)
        except ValueError:
            port = 22

        identity_file = entry.get("identityfile")
        if identity_file:
            identity_file = os.path.expanduser(identity_file)

        # Generate slugified host_id
        safe_alias = re.sub(r"[^a-zA-Z0-9_-]", "_", alias).lower()
        host_id = f"ssh_{safe_alias}"

        asset = SSHHostAsset(
            host_id=host_id,
            alias=alias,
            hostname=hostname,
            port=port,
            username=user,
            auth_method=HostAuthMethod.KEY_FILE if identity_file else HostAuthMethod.AGENT,
            key_path=identity_file,
            tags=["ssh_config_import"],
            created_at=time.time(),
            is_trusted=False,
        )
        target_list.append(asset)
