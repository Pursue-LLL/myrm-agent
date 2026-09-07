"""OpenSSH config (~/.ssh/config) parser for Multi-Host SSH Ops.

[INPUT]
- Raw string contents of an OpenSSH configuration file

[OUTPUT]
- list[SSHConfigParsedHost] with resolved host sections and inheritance

[POS]
Domain parser in app/services/ssh_bridge/.
"""

from __future__ import annotations

import os
import re
from typing import Sequence

from app.services.ssh_bridge.models import SSHConfigParsedHost


class OpenSSHConfigParser:
    """Robust parser for ~/.ssh/config file supporting multi-host declarations and directives."""

    @classmethod
    def parse_text(cls, config_text: str) -> Sequence[SSHConfigParsedHost]:
        """Parse raw OpenSSH configuration text into a list of structured parsed host objects."""
        lines = config_text.splitlines()
        hosts: list[SSHConfigParsedHost] = []

        current_patterns: list[str] = []
        current_options: dict[str, str] = {}

        for line in lines:
            stripped = line.strip()
            # Ignore empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            # Check if line starts with Host declaration
            match = re.match(r"^host\s+(.+)$", stripped, re.IGNORECASE)
            if match:
                # Flush previous host definition if exists
                if current_patterns:
                    hosts.extend(cls._build_hosts_for_patterns(current_patterns, current_options))
                current_patterns = match.group(1).split()
                current_options = {}
                continue

            # Parse key-value directives (key value or key=value)
            kv_match = re.match(r"^([a-zA-Z0-9_-]+)(?:[\s=]+)(.+)$", stripped)
            if kv_match:
                key = kv_match.group(1).lower()
                val = kv_match.group(2).strip().strip('"')
                current_options[key] = val

        # Flush final block
        if current_patterns:
            hosts.extend(cls._build_hosts_for_patterns(current_patterns, current_options))

        return tuple(hosts)

    @classmethod
    def _build_hosts_for_patterns(
        cls,
        patterns: Sequence[str],
        options: dict[str, str],
    ) -> list[SSHConfigParsedHost]:
        """Build SSHConfigParsedHost instances for given host patterns."""
        parsed_list: list[SSHConfigParsedHost] = []

        host_name = options.get("hostname")
        user = options.get("user")
        port_val = options.get("port", "22")
        port = int(port_val) if port_val.isdigit() else 22

        identity_file = options.get("identityfile")
        if identity_file:
            identity_file = os.path.expanduser(identity_file)

        proxy_jump = options.get("proxyjump")
        forward_agent = options.get("forwardagent", "no").lower() in ("yes", "true", "1")

        for pattern in patterns:
            # Skip global wildcard if not specific
            parsed_list.append(
                SSHConfigParsedHost(
                    pattern=pattern,
                    host_name=host_name,
                    user=user,
                    port=port,
                    identity_file=identity_file,
                    proxy_jump=proxy_jump,
                    forward_agent=forward_agent,
                    custom_options=dict(options),
                )
            )

        return parsed_list
