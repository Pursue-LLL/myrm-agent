"""MCP secret-aware authentication provider.

Resolves ``{{secret:KEY_NAME}}`` placeholders in MCP HTTP headers using the
agent's encrypted secret store (``DatabaseSecretBackend``).

Implements the harness-level ``MCPAuthProvider`` protocol so the framework's
``_inject_auth_headers`` injects resolved headers transparently.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.backends.secret_backend import DatabaseSecretBackend

logger = logging.getLogger(__name__)

_SECRET_REF_PATTERN = re.compile(r"\{\{secret:([^}]+)\}\}")


class MCPSecretAuthProvider:
    """Resolve ``{{secret:KEY}}`` references in MCP header values.

    Created per-agent in the factory; each instance holds a snapshot of the
    header template plus a reference to the secret store so values are
    resolved fresh on every connection attempt.
    """

    def __init__(
        self,
        header_templates: dict[str, str],
        secret_store: DatabaseSecretBackend,
        agent_id: str,
    ) -> None:
        self._header_templates = header_templates
        self._secret_store = secret_store
        self._agent_id = agent_id

    async def get_auth_headers(
        self, server_name: str, server_url: str
    ) -> dict[str, str]:
        """Return headers with all ``{{secret:KEY}}`` references resolved."""
        if not self._header_templates:
            return {}

        resolved: dict[str, str] = {}
        for header_name, template in self._header_templates.items():
            refs = _SECRET_REF_PATTERN.findall(template)
            if not refs:
                resolved[header_name] = template
                continue

            value = template
            for key_name in refs:
                secret_value = await self._secret_store.get_secret(
                    self._agent_id, key_name
                )
                if secret_value is None:
                    logger.warning(
                        "MCP '%s': header '%s' references secret '%s' "
                        "which does not exist for agent %s — "
                        "keeping placeholder (server will likely reject)",
                        server_name,
                        header_name,
                        key_name,
                        self._agent_id,
                    )
                    continue
                value = value.replace(f"{{{{secret:{key_name}}}}}", secret_value)

            resolved[header_name] = value

        return resolved
