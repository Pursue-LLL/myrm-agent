"""Connect service: manage external agent connections.

[INPUT]
- app.core.infra.ingress::get_public_ingress_base_url (POS: Resolve ingress URL)
- app.config.settings::settings (POS: Application settings)
- app.config.deploy_mode::is_local_mode (POS: Deployment-mode detection)
- app.services.connect.profiles::ConnectionProfile (POS: External agent profile registry)
- app.services.connect.doctor_check::verify_connector_config (POS: On-disk MCP config verification)

[OUTPUT]
- ConnectService: orchestrates connection profiles, tokens, and health checks.
- DoctorResult: doctor check outcome with a machine-readable detail code.

[POS]
Manages external AI agent (Claude Code, Cursor, Windsurf, etc.) connections
to our memory MCP server. Generates config snippets, API tokens, and performs
health checks. Business logic for the Connect Wizard feature.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.deploy_mode import is_local_mode
from app.config.settings import settings
from app.services.connect.doctor_check import (
    DOCTOR_TOKEN_VALID,
    DOCTOR_UNKNOWN,
    DoctorSeverity,
    DoctorVerdict,
    hash_token,
    verify_connector_config,
)
from app.services.connect.profiles import PROFILES, ConnectionProfile

if TYPE_CHECKING:
    from app.services.connect.agent_plugin import AgentPluginBundle

logger = logging.getLogger(__name__)


class ConnectorStatus(str, Enum):
    """Connection readiness status."""

    READY = "ready"
    CONFIGURED = "manual_config_required"
    MISSING = "missing"


@dataclass
class ConnectorState:
    """Persisted state of a connector."""

    profile_id: str
    status: ConnectorStatus = ConnectorStatus.MISSING
    token_hash: str = ""
    agent_id: str = "default"
    connected_at: datetime | None = None
    last_doctor_at: datetime | None = None
    doctor_ok: bool = False
    last_doctor_detail: str = ""
    expose_desktop: bool = False


@dataclass(frozen=True)
class VerifiedConnectToken:
    """Resolved MCP bearer token binding."""

    profile_id: str
    agent_id: str
    expose_desktop: bool = False


@dataclass(frozen=True)
class DoctorResult:
    """Outcome of a connector doctor check."""

    healthy: bool
    detail: str
    severity: DoctorSeverity = "error"


@dataclass
class ConfigSnippet:
    """Generated config snippet for an external agent."""

    profile_id: str
    agent_id: str
    config_json: dict[str, object]
    mcp_url: str
    token: str
    instructions: str
    expose_desktop: bool = False


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
                    agent_id=self._normalize_agent_id(data.get("agent_id")),
                    connected_at=(datetime.fromisoformat(data["connected_at"]) if data.get("connected_at") else None),
                    last_doctor_at=(datetime.fromisoformat(data["last_doctor_at"]) if data.get("last_doctor_at") else None),
                    doctor_ok=data.get("doctor_ok", False),
                    last_doctor_detail=data.get("last_doctor_detail", ""),
                    expose_desktop=bool(data.get("expose_desktop", False)),
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
                "agent_id": state.agent_id,
                "connected_at": (state.connected_at.isoformat() if state.connected_at else None),
                "last_doctor_at": (state.last_doctor_at.isoformat() if state.last_doctor_at else None),
                "doctor_ok": state.doctor_ok,
                "last_doctor_detail": state.last_doctor_detail,
                "expose_desktop": state.expose_desktop,
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

    async def generate_config(
        self,
        profile_id: str,
        *,
        agent_id: str = "default",
        expose_desktop: bool = False,
    ) -> ConfigSnippet:
        """Generate MCP config snippet and token for an external agent.

        Creates a new API token, generates the appropriate JSON config,
        and persists the connection state scoped to a Myrm Agent Profile.
        """
        if profile_id not in PROFILES:
            msg = f"Unknown profile: {profile_id}"
            raise ValueError(msg)

        normalized_agent_id = self._normalize_agent_id(agent_id)
        profile = PROFILES[profile_id]
        token = self._generate_token()

        from app.core.infra.ingress import get_public_ingress_base_url
        from app.services.connect.snippet_builder import build_config_json, build_instructions

        base_url = await get_public_ingress_base_url()
        if not base_url:
            base_url = f"http://127.0.0.1:{settings.port}"

        mcp_url = f"{base_url}/mcp"

        config_json = build_config_json(profile, mcp_url, token, expose_desktop=expose_desktop)
        instructions = build_instructions(profile, mcp_url, expose_desktop=expose_desktop)

        self._states[profile_id] = ConnectorState(
            profile_id=profile_id,
            status=ConnectorStatus.CONFIGURED,
            token_hash=hash_token(token),
            agent_id=normalized_agent_id,
            expose_desktop=expose_desktop,
        )
        self._save_state()

        return ConfigSnippet(
            profile_id=profile_id,
            agent_id=normalized_agent_id,
            config_json=config_json,
            mcp_url=mcp_url,
            token=token,
            instructions=instructions,
            expose_desktop=expose_desktop,
        )

    def resolve_token(self, token: str) -> VerifiedConnectToken | None:
        """Verify an MCP bearer token and return its external + memory scope binding."""
        token_hash = hash_token(token)
        for pid, state in self._states.items():
            if state.token_hash and state.token_hash == token_hash:
                return VerifiedConnectToken(
                    profile_id=pid,
                    agent_id=state.agent_id,
                    expose_desktop=state.expose_desktop,
                )
        return None

    async def generate_agent_plugin_bundle(self, *, agent_id: str = "default", embed_token: bool = False) -> "AgentPluginBundle":
        """Generate a portable Agent Plugins 1.0.0 bundle exposing Myrm memory."""
        from app.core.infra.ingress import get_public_ingress_base_url
        from app.services.connect.agent_plugin import (
            AGENT_PLUGIN_PROFILE,
            build_agent_plugin_bundle,
        )

        token = self._generate_token()
        normalized = self._normalize_agent_id(agent_id)
        base_url = await get_public_ingress_base_url()
        if not base_url:
            base_url = f"http://127.0.0.1:{settings.port}"
        self._states[AGENT_PLUGIN_PROFILE] = ConnectorState(
            profile_id=AGENT_PLUGIN_PROFILE,
            status=ConnectorStatus.CONFIGURED,
            token_hash=hash_token(token),
            agent_id=normalized,
        )
        self._save_state()
        return build_agent_plugin_bundle(f"{base_url}/mcp", token, agent_id=normalized, embed_token=embed_token)

    async def doctor(self, profile_id: str) -> DoctorResult:
        """Run a health check on a connector.

        In local/Tauri deployments the external agent's on-disk config file is
        verified directly (``myrm-memory`` entry + token match). In sandbox mode
        the config lives on the user's machine, so only token validity is
        reported and the limitation is surfaced through the detail code.

        The check only records ``doctor_ok``/``last_doctor_detail``/``last_doctor_at``;
        the lifecycle ``status`` is left untouched (it is driven by
        generate/mark_ready/revoke).
        """
        if profile_id not in self._states:
            return DoctorResult(healthy=False, detail=DOCTOR_UNKNOWN)
        state = self._states[profile_id]
        state.last_doctor_at = datetime.now(UTC)

        verdict: DoctorVerdict | None = None
        profile = PROFILES.get(profile_id)
        if is_local_mode() and profile is not None and state.token_hash:
            verdict = await asyncio.to_thread(
                verify_connector_config,
                config_file_path=profile.config_file_path,
                instructions_key=profile.instructions_key,
                config_format=profile.config_format,
                token_hash=state.token_hash,
            )

        if verdict is not None:
            healthy, detail, severity = verdict.healthy, verdict.detail, verdict.severity
        else:
            healthy = bool(state.token_hash) and state.status != ConnectorStatus.MISSING
            detail = DOCTOR_TOKEN_VALID if healthy else DOCTOR_UNKNOWN
            # Token validity cannot be verified against an agent-side config in
            # sandbox mode; that is a warn-level blind spot, not an error.
            severity: DoctorSeverity = "warn" if healthy else "error"

        # A doctor result describes config/token health only; it must not promote
        # the lifecycle status (READY is set by mark_ready on real MCP traffic).
        state.doctor_ok = healthy
        state.last_doctor_detail = detail
        if severity == "error":
            logger.warning(
                "Connector doctor check failed: profile=%s detail=%s",
                profile_id,
                detail,
            )
        elif severity == "warn":
            logger.info(
                "Connector doctor check: profile=%s detail=%s (not verifiable)",
                profile_id,
                detail,
            )
        self._save_state()
        return DoctorResult(healthy=healthy, detail=detail, severity=severity)

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
        """Mark a connector as ready on its first successful MCP request.

        ``doctor_ok`` reflects only the last doctor check result, not the mere
        existence of an MCP call. ``connected_at`` records the first real
        connection time, kept separate from config-generation time.
        """
        if profile_id not in self._states:
            return
        state = self._states[profile_id]
        if state.status == ConnectorStatus.READY:
            return
        state.status = ConnectorStatus.READY
        if state.connected_at is None:
            state.connected_at = datetime.now(UTC)
        self._save_state()

    @staticmethod
    def _normalize_agent_id(agent_id: object | None) -> str:
        if not isinstance(agent_id, str):
            return "default"
        normalized = agent_id.strip()
        return normalized or "default"

    @staticmethod
    def _generate_token() -> str:
        """Generate a secure API token."""
        return f"myrm_mcp_{secrets.token_urlsafe(32)}"


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
    "DoctorResult",
    "VerifiedConnectToken",
    "get_connect_service",
]
