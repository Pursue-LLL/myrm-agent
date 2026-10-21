"""Protected Change Window and Break-Glass authorization service for SSH Vault.

[INPUT]
- .models::SSHHostConfig
- secrets, hashlib, time, datetime, logging

[OUTPUT]
- ProtectedChangeWindowService: Coordinator for change window policies, break-glass tokens, and audit trails
- BreakGlassTokenData, BreakGlassAuditRecord

[POS]
Domain service in app/services/ssh_vault/change_window.py.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

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
    raw_command_preview: str = ""


@dataclass
class BreakGlassAuditRecord:
    """Immutable audit record generated whenever break-glass token is issued or consumed."""

    event_type: str  # "ISSUED" | "CONSUMED" | "EXPIRED" | "REJECTED"
    token: str
    host_alias: str
    command: str
    reason: str
    timestamp_utc: str
    success: bool
    details: str = ""


class ProtectedChangeWindowService:
    """Coordinates environment tiers, maintenance windows, and break-glass token lifecycles."""

    def __init__(self, max_audit_records: int = 500) -> None:
        self._tokens: dict[str, BreakGlassTokenData] = {}
        self._audit_records: list[BreakGlassAuditRecord] = []
        self._max_audit_records = max_audit_records

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
        cmd_preview = command.strip()[:100]

        record = BreakGlassTokenData(
            token=token_str,
            host_alias=host_alias,
            command_fingerprint=cmd_fp,
            reason=reason or "Emergency state mutation break-glass",
            issued_at=now,
            expires_at=now + ttl_seconds,
            consumed=False,
            raw_command_preview=cmd_preview,
        )
        self._tokens[token_str] = record

        self._record_audit(
            event_type="ISSUED",
            token=token_str,
            host_alias=host_alias,
            command=cmd_preview,
            reason=reason,
            success=True,
            details=f"Valid for {ttl_seconds}s until {datetime.fromtimestamp(now + ttl_seconds, tz=timezone.utc).isoformat()}",
        )
        logger.warning(
            "[BREAK_GLASS_ISSUED] token=%s host=%s reason=%s cmd_fp=%s",
            token_str,
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
            self._record_audit(
                event_type="REJECTED",
                token=token,
                host_alias=host_alias,
                command=command[:100],
                reason="",
                success=False,
                details="Token not found in active registry",
            )
            return False, "Break-glass token not found or invalid"

        if record.consumed:
            self._record_audit(
                event_type="REJECTED",
                token=token,
                host_alias=host_alias,
                command=command[:100],
                reason=record.reason,
                success=False,
                details="Token already consumed (single-use policy)",
            )
            return False, "Break-glass token has already been consumed (single-use violation)"

        now = time.time()
        if now > record.expires_at:
            self._record_audit(
                event_type="EXPIRED",
                token=token,
                host_alias=host_alias,
                command=command[:100],
                reason=record.reason,
                success=False,
                details=f"Token expired at {record.expires_at}, current time is {now}",
            )
            return False, "Break-glass token has expired"

        if record.host_alias != host_alias:
            self._record_audit(
                event_type="REJECTED",
                token=token,
                host_alias=host_alias,
                command=command[:100],
                reason=record.reason,
                success=False,
                details=f"Host mismatch: bound to '{record.host_alias}' but invoked on '{host_alias}'",
            )
            return False, f"Break-glass token is bound to host '{record.host_alias}', not '{host_alias}'"

        current_fp = _fingerprint_command(command)
        if record.command_fingerprint != current_fp:
            self._record_audit(
                event_type="REJECTED",
                token=token,
                host_alias=host_alias,
                command=command[:100],
                reason=record.reason,
                success=False,
                details="Command hash mismatch: command was altered after token issuance",
            )
            return False, "Break-glass token command mismatch: command was modified after approval"

        # Atomically consume
        record.consumed = True
        self._record_audit(
            event_type="CONSUMED",
            token=token,
            host_alias=host_alias,
            command=command[:100],
            reason=record.reason,
            success=True,
            details="Successfully authorized and consumed single-use token",
        )
        logger.warning(
            "[BREAK_GLASS_CONSUMED] Successfully authorized write command on host=%s: %s",
            host_alias,
            command[:100],
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

    def get_audit_trail(self, limit: int = 50) -> list[BreakGlassAuditRecord]:
        """Retrieve recent break-glass audit logs."""
        return self._audit_records[-limit:]

    def _record_audit(
        self,
        event_type: str,
        token: str,
        host_alias: str,
        command: str,
        reason: str,
        success: bool,
        details: str = "",
    ) -> None:
        rec = BreakGlassAuditRecord(
            event_type=event_type,
            token=token[:10] + "...",
            host_alias=host_alias,
            command=command,
            reason=reason,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            success=success,
            details=details,
        )
        self._audit_records.append(rec)
        if len(self._audit_records) > self._max_audit_records:
            self._audit_records = self._audit_records[-self._max_audit_records :]
