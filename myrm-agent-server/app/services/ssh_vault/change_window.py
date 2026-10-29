"""Protected Change Window and Break-Glass authorization service for SSH Vault.

[INPUT]
- .models::SSHHostConfig
- secrets, hashlib, time, logging
- myrm_agent_harness.api::command_preview (a log line shows the command masked and cut)

[OUTPUT]
- ProtectedChangeWindowService: Coordinator for change window policies and the single-use break-glass token lifecycle
- BreakGlassTokenData

[POS]
Domain service in app/services/ssh_vault/change_window.py.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Final

from myrm_agent_harness.api import command_preview

from app.services.ssh_vault.models import SSHHostConfig

logger = logging.getLogger("myrm.services.ssh_vault.change_window")

_DEFAULT_BREAK_GLASS_TTL_SECONDS: Final[int] = 300  # 5 minutes


def _fingerprint_command(command: str) -> str:
    """Create a deterministic SHA-256 fingerprint for command matching."""
    return hashlib.sha256(command.strip().encode("utf-8")).hexdigest()


@dataclass
class BreakGlassTokenData:
    """Metadata for an active or consumed break-glass authorization token."""

    token: str
    host_alias: str
    command_fingerprint: str
    reason: str
    issued_at: float
    expires_at: float
    consumed: bool = False


class ProtectedChangeWindowService:
    """Coordinates environment tiers, maintenance windows, and break-glass token lifecycles."""

    def __init__(self) -> None:
        self._tokens: dict[str, BreakGlassTokenData] = {}

    def issue_break_glass_token(
        self,
        host_alias: str,
        command: str,
        reason: str,
        ttl_seconds: int = _DEFAULT_BREAK_GLASS_TTL_SECONDS,
    ) -> BreakGlassTokenData:
        """Issue a single-use, time-bound break-glass authorization token for a specific command."""
        now = time.time()
        token_str = f"bg_{secrets.token_urlsafe(24)}"
        cmd_fp = _fingerprint_command(command)

        record = BreakGlassTokenData(
            token=token_str,
            host_alias=host_alias,
            command_fingerprint=cmd_fp,
            reason=reason or "Emergency state mutation break-glass",
            issued_at=now,
            expires_at=now + ttl_seconds,
            consumed=False,
        )
        self._tokens[token_str] = record

        logger.warning(
            "[BREAK_GLASS_ISSUED] host=%s reason=%s cmd_fp=%s",
            host_alias,
            reason,
            cmd_fp[:12],
        )
        return record

    def verify_and_consume_token(
        self,
        token: str,
        host_alias: str,
        command: str,
    ) -> tuple[bool, str]:
        """Verify token authenticity, scope, expiration, and consume it atomically."""
        if not token:
            return False, "No break-glass token provided"

        record = self._tokens.get(token)
        if not record:
            return False, "Break-glass token not found or invalid"

        if record.consumed:
            return False, "Break-glass token has already been consumed (single-use violation)"

        now = time.time()
        if now > record.expires_at:
            return False, "Break-glass token has expired"

        if record.host_alias != host_alias:
            return False, f"Break-glass token is bound to host '{record.host_alias}', not '{host_alias}'"

        current_fp = _fingerprint_command(command)
        if record.command_fingerprint != current_fp:
            return False, "Break-glass token command mismatch: command was modified after approval"

        # Atomically consume
        record.consumed = True
        logger.warning(
            "[BREAK_GLASS_CONSUMED] Successfully authorized write command on host=%s: %s",
            host_alias,
            command_preview(command, 100),
        )
        return True, ""

    def evaluate_write_authorization(
        self,
        host_config: SSHHostConfig,
        command: str,
        break_glass_token: str | None = None,
    ) -> tuple[bool, str, bool]:
        """Evaluate if a write/state-mutating command is authorized to execute.

        Returns:
            Tuple of (is_authorized, reason, break_glass_token_used).
        """
        # If host does not enforce read-only, write is allowed directly
        if not host_config.is_read_only:
            return True, "Host is in read-write mode", False

        # Host enforces read-only: require break-glass authorization
        if break_glass_token:
            is_valid, err_msg = self.verify_and_consume_token(
                token=break_glass_token,
                host_alias=host_config.host_alias,
                command=command,
            )
            if is_valid:
                return True, "Authorized via Break-Glass token", True
            return False, f"Break-Glass authorization failed: {err_msg}", False

        # No token provided
        tier = host_config.environment_tier
        reason = (
            f"Host '{host_config.host_alias}' ({tier}) is locked under strict Read-Only protection. "
            "State-mutating commands require explicit user Break-Glass approval."
        )
        return False, reason, False
