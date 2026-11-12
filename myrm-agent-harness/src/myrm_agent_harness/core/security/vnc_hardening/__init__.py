"""VNC Loopback Bind and Rfbauth Hardening Suite.

[INPUT]
- core.security.vnc_hardening.config_sanitizer::VncLaunchConfigSanitizer (POS: Launch-command leg of the VNC hardening suite: requires an rfbauth password file, strips -nopw, binds to loopback unless a non-loopback opt-in with a strong dedicated password is given, checks the password file permissions and builds the x11vnc argument list.)
- core.security.vnc_hardening.facade::VncLoopbackBindAndRfbauthHardeningFacade (POS: Entry point of the VNC hardening suite: builds a hardened x11vnc launch spec from a launch config, audits a raw argument list for -nopw, a missing -rfbauth and a missing -localhost, and exposes password generation and strength checks.)
- core.security.vnc_hardening.passwd_manager::VncPasswdManager, VncSecurityError (POS: Credential leg of the VNC hardening suite: judges password strength (at least 8 characters with a letter and a digit), generates random passwords, and tightens the rfbauth password file to owner-only 0600.)
- core.security.vnc_hardening.types::VncAuthPolicy, VncBindMode, VncHardenedLaunchSpec, VncHardeningAuditReport, VncLaunchConfig, VncSecurityAuditViolation, VncSecurityViolationType (POS: Contract layer of the VNC hardening suite: the bind-mode, auth-policy and violation enums plus the launch-config, hardened-spec, violation and report models shared by the sanitizer and the facade.)

[OUTPUT]
- the facade, the sanitizer, the password manager and the domain types listed in `__all__`

[POS]
Package facade of the VNC hardening suite: the single import point for the facade, the sanitizer, the password manager and
the domain types.
"""

from __future__ import annotations

from .config_sanitizer import VncLaunchConfigSanitizer
from .facade import VncLoopbackBindAndRfbauthHardeningFacade
from .passwd_manager import VncPasswdManager, VncSecurityError
from .types import (
    VncAuthPolicy,
    VncBindMode,
    VncHardenedLaunchSpec,
    VncHardeningAuditReport,
    VncLaunchConfig,
    VncSecurityAuditViolation,
    VncSecurityViolationType,
)

__all__ = [
    "VncAuthPolicy",
    "VncBindMode",
    "VncHardenedLaunchSpec",
    "VncHardeningAuditReport",
    "VncLaunchConfig",
    "VncLaunchConfigSanitizer",
    "VncLoopbackBindAndRfbauthHardeningFacade",
    "VncPasswdManager",
    "VncSecurityAuditViolation",
    "VncSecurityError",
    "VncSecurityViolationType",
]
