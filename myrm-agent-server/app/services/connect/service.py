"""Connect service: manage external agent connections.

[INPUT]
- app.core.infra.ingress::get_public_ingress_base_url (POS: Resolve ingress URL)
- app.config.settings::settings (POS: Application settings)

[OUTPUT]
- ConnectService: orchestrates connection profiles, tokens, and health checks.
- ConnectionProfile: describes an external agent type and how to connect it.

[POS]
Manages external AI agent (Claude Code, Cursor, Windsurf, etc.) connections
to our memory MCP server. Generates config snippets, API tokens, and performs
health checks. Business logic for the Connect Wizard feature.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from app.config.settings import settings

logger = logging.getLogger(__name__)


class ConnectorStatus(str, Enum):
    """Connection readiness status."""

    READY = "ready"
    CONFIGURED = "manual_config_required"
    MISSING = "missing"


@dataclass(frozen=True)
class ConnectionProfile:
    """Describes how a specific external agent connects to our MCP server."""

    id: str
    label: str
    description: str
    config_format: Literal["json_mcp", "toml_mcp", "claude_hooks"]
    config_file_path: str
    instructions_key: str


# Supported external agents and their MCP config details
PROFILES: dict[str, ConnectionProfile] = {
    "claude_code": ConnectionProfile(
        id="claude_code",
        label="Claude Code",
        description="Anthropic's Claude Code CLI agent",
        config_format="json_mcp",
        config_file_path="~/.claude.json",
        instructions_key="mcpServers",
    ),
    "cursor": ConnectionProfile(
        id="cursor",
        label="Cursor",
        description="Cursor IDE AI assistant",
        config_format="json_mcp",
        config_file_path="~/.cursor/mcp.json",
        instructions_key="mcpServers",
    ),
    "windsurf": ConnectionProfile(
        id="windsurf",
        label="Windsurf",
        description="Codeium Windsurf IDE agent",
        config_format="json_mcp",
        config_file_path="~/.codeium/windsurf/mcp_config.json",
        instructions_key="mcpServers",
    ),
    "codex": ConnectionProfile(
        id="codex",
        label="Codex CLI",
        description="OpenAI Codex CLI agent",
        config_format="toml_mcp",
        config_file_path="~/.codex/config.toml",
        instructions_key="mcp_servers",
    ),
    "gemini_cli": ConnectionProfile(
        id="gemini_cli",
        label="Gemini CLI",
        description="Google Gemini CLI agent",
        config_format="json_mcp",
        config_file_path="~/.gemini/settings.json",
        instructions_key="mcpServers",
    ),
}


@dataclass
class ConnectorState:
    """Persisted state of a connector."""

    profile_id: str
    status: ConnectorStatus = ConnectorStatus.MISSING
    token_hash: str = ""
    connected_at: datetime | None = None
    last_doctor_at: datetime | None = None
    doctor_ok: bool = False


@dataclass
class ConfigSnippet:
    """Generated config snippet for an external agent."""

    profile_id: str
    config_json: dict[str, object]
    mcp_url: str
    token: str
    instructions: str


class ConnectService:
    """Service managing external agent connections.

    Stores connector state in a JSON file within the data directory.
    Generates tokens, config snippets, and performs doctor checks.
    """

    _STATE_FILE = "connect_state.json"

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or Path(settings.database.state_dir)
        self._states: dict[str, ConnectorState] = {}
        self._load_state()

    def _state_path(self) -> Path:
        return self._data_dir / self._STATE_FILE

    def _load_state(self) -> None:
        path = self._state_path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text())
            for profile_id, data in raw.items():
                self._states[profile_id] = ConnectorState(
                    profile_id=profile_id,
                    status=ConnectorStatus(data.get("status", "missing")),
                    token_hash=data.get("token_hash", ""),
                    connected_at=datetime.fromisoformat(data["connected_at"]) if data.get("connected_at") else None,
                    last_doctor_at=datetime.fromisoformat(data["last_doctor_at"]) if data.get("last_doctor_at") else None,
                    doctor_ok=data.get("doctor_ok", False),
                )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Failed to load connect state, starting fresh: %s", e)
            self._states = {}

    def _save_state(self) -> None:
        path = self._state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, object] = {}
        for profile_id, state in self._states.items():
            data[profile_id] = {
                "status": state.status.value,
                "token_hash": state.token_hash,
                "connected_at": state.connected_at.isoformat() if state.connected_at else None,
                "last_doctor_at": state.last_doctor_at.isoformat() if state.last_doctor_at else None,
                "doctor_ok": state.doctor_ok,
            }
        path.write_text(json.dumps(data, indent=2))

    def list_profiles(self) -> list[ConnectionProfile]:
        """Return all supported connection profiles."""
        return list(PROFILES.values())

    def get_connector_status(self, profile_id: str) -> ConnectorState:
        """Get current state of a connector."""
        if profile_id not in self._states:
            return ConnectorState(profile_id=profile_id)
        return self._states[profile_id]

    def list_all_states(self) -> list[ConnectorState]:
        """Return states for all known profiles (including unconfigured)."""
        result: list[ConnectorState] = []
        for pid in PROFILES:
            result.append(self.get_connector_status(pid))
        return result

    async def generate_config(self, profile_id: str) -> ConfigSnippet:
        """Generate MCP config snippet and token for an external agent.

        Creates a new API token, generates the appropriate JSON config,
        and persists the connection state.
        """
        if profile_id not in PROFILES:
            msg = f"Unknown profile: {profile_id}"
            raise ValueError(msg)

        profile = PROFILES[profile_id]
        token = self._generate_token()

        from app.core.infra.ingress import get_public_ingress_base_url

        base_url = await get_public_ingress_base_url()
        if not base_url:
            base_url = f"http://127.0.0.1:{settings.port}"

        mcp_url = f"{base_url}/mcp"

        config_json = self._build_config_json(profile, mcp_url, token)
        instructions = self._build_instructions(profile, mcp_url)

        self._states[profile_id] = ConnectorState(
            profile_id=profile_id,
            status=ConnectorStatus.CONFIGURED,
            token_hash=self._hash_token(token),
            connected_at=datetime.now(UTC),
        )
        self._save_state()

        return ConfigSnippet(
            profile_id=profile_id,
            config_json=config_json,
            mcp_url=mcp_url,
            token=token,
            instructions=instructions,
        )

    def verify_token(self, token: str) -> str | None:
        """Verify an incoming MCP token, return profile_id if valid."""
        token_hash = self._hash_token(token)
        for pid, state in self._states.items():
            if state.token_hash and state.token_hash == token_hash:
                return pid
        return None

    async def doctor(self, profile_id: str) -> bool:
        """Run a health check on a connector.

        Verifies the token is still valid and the connector state is active.
        """
        if profile_id not in self._states:
            return False
        state = self._states[profile_id]
        is_healthy = bool(state.token_hash) and state.status != ConnectorStatus.MISSING
        state.last_doctor_at = datetime.now(UTC)
        state.doctor_ok = is_healthy
        if is_healthy:
            state.status = ConnectorStatus.READY
        self._save_state()
        return is_healthy

    def revoke(self, profile_id: str) -> bool:
        """Revoke a connector's token and reset its state."""
        if profile_id not in self._states:
            return False
        self._states[profile_id] = ConnectorState(
            profile_id=profile_id,
            status=ConnectorStatus.MISSING,
        )
        self._save_state()
        return True

    def mark_ready(self, profile_id: str) -> None:
        """Mark a connector as ready (called on first successful MCP request)."""
        if profile_id not in self._states:
            return
        state = self._states[profile_id]
        if state.status == ConnectorStatus.READY:
            return
        state.status = ConnectorStatus.READY
        state.doctor_ok = True
        state.last_doctor_at = datetime.now(UTC)
        self._save_state()

    @staticmethod
    def _generate_token() -> str:
        """Generate a secure API token."""
        return f"myrm_mcp_{secrets.token_urlsafe(32)}"

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash a token for storage (SHA-256)."""
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _build_config_json(profile: ConnectionProfile, mcp_url: str, token: str) -> dict[str, object]:
        """Build the MCP config snippet for the external agent's config file.

        For TOML-based agents (Codex), returns a dict representation that
        the frontend displays as TOML. For JSON-based agents, returns the
        standard JSON config structure.
        """
        if profile.config_format == "toml_mcp":
            return {
                "_format": "toml",
                "_toml_snippet": (
                    f"[{profile.instructions_key}.myrm-memory]\n"
                    f'url = "{mcp_url}"\n'
                    f'transport = "streamable-http"\n\n'
                    f"[{profile.instructions_key}.myrm-memory.headers]\n"
                    f'Authorization = "Bearer {token}"\n'
                ),
                profile.instructions_key: {
                    "myrm-memory": {
                        "url": mcp_url,
                        "transport": "streamable-http",
                        "headers": {"Authorization": f"Bearer {token}"},
                    }
                },
            }
        return {
            profile.instructions_key: {
                "myrm-memory": {
                    "url": mcp_url,
                    "transport": "streamable-http",
                    "headers": {"Authorization": f"Bearer {token}"},
                }
            }
        }

    @staticmethod
    def _build_instructions(profile: ConnectionProfile, mcp_url: str) -> str:
        """Build human-readable setup instructions."""
        return (
            f"Add the following to your {profile.config_file_path}:\n"
            f"Under '{profile.instructions_key}', add a 'myrm-memory' entry "
            f"pointing to {mcp_url} with the generated Bearer token."
        )


# Module singleton (lazily initialized per request in API layer)
_service: ConnectService | None = None


def get_connect_service() -> ConnectService:
    """Get or create the ConnectService singleton."""
    global _service
    if _service is None:
        _service = ConnectService()
    return _service


__all__ = [
    "PROFILES",
    "ConfigSnippet",
    "ConnectService",
    "ConnectionProfile",
    "ConnectorState",
    "ConnectorStatus",
    "get_connect_service",
]
