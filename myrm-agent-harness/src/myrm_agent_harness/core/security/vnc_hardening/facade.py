"""Unified facade for VNC loopback bind enforcement and rfbauth authentication hardening.

[INPUT]
- core.security.vnc_hardening.config_sanitizer::VncLaunchConfigSanitizer (POS: Launch-command leg of the VNC hardening suite: requires an rfbauth password file, strips -nopw, binds to loopback unless a non-loopback opt-in with a strong dedicated password is given, checks the password file permissions and builds the x11vnc argument list.)
- core.security.vnc_hardening.passwd_manager::VncPasswdManager (POS: Credential leg of the VNC hardening suite: judges password strength (at least 8 characters with a letter and a digit), generates random passwords, and tightens the rfbauth password file to owner-only 0600.)
- core.security.vnc_hardening.types::VncBindMode, VncHardenedLaunchSpec, VncHardeningAuditReport, VncLaunchConfig, VncSecurityAuditViolation, VncSecurityViolationType (POS: Contract layer of the VNC hardening suite: the bind-mode, auth-policy and violation enums plus the launch-config, hardened-spec, violation and report models shared by the sanitizer and the facade.)

[OUTPUT]
- VncLoopbackBindAndRfbauthHardeningFacade: hardened launch spec builder, raw command auditor and password helpers behind one object

[POS]
Entry point of the VNC hardening suite: builds a hardened x11vnc launch spec from a launch config, audits a raw argument
list for -nopw, a missing -rfbauth and a missing -localhost, and exposes password generation and strength checks.
"""

from __future__ import annotations

import logging
import time

from .config_sanitizer import VncLaunchConfigSanitizer
from .passwd_manager import VncPasswdManager
from .types import (
    VncBindMode,
    VncHardenedLaunchSpec,
    VncHardeningAuditReport,
    VncLaunchConfig,
    VncSecurityAuditViolation,
    VncSecurityViolationType,
)

logger = logging.getLogger(__name__)


class VncLoopbackBindAndRfbauthHardeningFacade:
    """Unified entrypoint for VNC loopback default, -nopw elimination, and rfbauth verification."""

    def __init__(
        self,
        sanitizer: VncLaunchConfigSanitizer | None = None,
        passwd_manager: VncPasswdManager | None = None,
    ) -> None:
        self._passwd_mgr = passwd_manager or VncPasswdManager()
        self._sanitizer = sanitizer or VncLaunchConfigSanitizer(self._passwd_mgr)

    @property
    def sanitizer(self) -> VncLaunchConfigSanitizer:
        """Underlying configuration sanitizer."""
        return self._sanitizer

    @property
    def passwd_manager(self) -> VncPasswdManager:
        """Underlying password manager."""
        return self._passwd_mgr

    def sanitize_launch_config(
        self,
        config: VncLaunchConfig,
        auto_remediate: bool = True,
    ) -> VncHardenedLaunchSpec:
        """Build hardened launch command, stripping -nopw and injecting -localhost by default."""
        return self._sanitizer.sanitize(config, auto_remediate=auto_remediate)

    def audit_raw_command(self, args: list[str]) -> VncHardeningAuditReport:
        """Inspect a raw command argument list for security exposures and return compliance report."""
        violations: list[VncSecurityAuditViolation] = []
        remediation_summary: list[str] = []

        has_rfbauth = False
        rfbauth_path = ""
        has_localhost = False
        has_nopw = False

        for i, arg in enumerate(args):
            clean = arg.strip()
            if clean == "-nopw":
                has_nopw = True
                violations.append(
                    VncSecurityAuditViolation(
                        violation_type=VncSecurityViolationType.NOPW_CONFLICT,
                        description="Dangerous '-nopw' flag disables password authentication completely",
                        flag_or_path="-nopw",
                        auto_remediated=False,
                    )
                )
            elif clean == "-localhost":
                has_localhost = True
            elif clean == "-rfbauth":
                has_rfbauth = True
                if i + 1 < len(args):
                    rfbauth_path = args[i + 1]

        if not has_rfbauth or not rfbauth_path:
            violations.append(
                VncSecurityAuditViolation(
                    violation_type=VncSecurityViolationType.MISSING_RFBAUTH,
                    description="Missing '-rfbauth <path>' flag; native RFB requires authentication",
                    flag_or_path="-rfbauth",
                    auto_remediated=False,
                )
            )

        if not has_localhost:
            violations.append(
                VncSecurityAuditViolation(
                    violation_type=VncSecurityViolationType.UNPROTECTED_NON_LOOPBACK,
                    description="Missing '-localhost' flag; exposes VNC port on all network interfaces",
                    flag_or_path="all_interfaces",
                    auto_remediated=False,
                )
            )

        # Synthesize remediation summary
        if has_nopw:
            remediation_summary.append("Strip '-nopw' to ensure rfbauth is honored")
        if not has_localhost:
            remediation_summary.append("Append '-localhost' to restrict listening to 127.0.0.1")
        if not has_rfbauth:
            remediation_summary.append("Enforce '-rfbauth <passwd_file>' authentication")

        verdict = "PASS" if not violations else "BLOCKED"

        spec = VncHardenedLaunchSpec(
            command_args=list(args),
            effective_bind_mode=VncBindMode.LOOPBACK if has_localhost else VncBindMode.NON_LOOPBACK_OPT_IN,
            rfbauth_path=rfbauth_path,
            violations=violations,
            is_hardened=verdict == "PASS",
        )

        return VncHardeningAuditReport(
            timestamp=time.time(),
            spec=spec,
            verdict=verdict,
            remediation_summary=remediation_summary,
        )

    def generate_secure_vnc_password(self, length: int = 14) -> str:
        """Generate high-entropy random password satisfying complexity policies."""
        return self._passwd_mgr.generate_secure_password(length)

    def evaluate_password(self, password: str) -> tuple[bool, str]:
        """Validate password meets minimum complexity requirements."""
        return self._passwd_mgr.evaluate_password_strength(password)
