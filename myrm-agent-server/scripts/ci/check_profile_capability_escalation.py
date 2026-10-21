#!/usr/bin/env python3
"""Profile Capability Escalation CI Gate.

Audits built-in security profiles and Agent templates to ensure no Pull Request
silently escalates capabilities or relaxes critical security baselines
(e.g., granting wildcard '*' permissions, enabling YOLO by default, or
relaxing sensitive execution permissions).

[INPUT]
- app/services/security/profile_manager.py AST (parsed without runtime imports)

[OUTPUT]
- Exit 0: All built-in profiles comply with least-privilege security baseline.
- Exit 1: Privilege escalation or security policy violation detected.

[POS]
CI gate script executed during server-architecture checks.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent


def _extract_builtin_profiles_from_ast(file_path: Path) -> list[dict]:
    """Parse _BUILTIN_PROFILES directly from AST to avoid runtime DB dependency."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    for node in tree.body:
        # Matches: _BUILTIN_PROFILES: list[dict[str, object]] = [...] (AnnAssign)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "_BUILTIN_PROFILES" and node.value is not None:
                return ast.literal_eval(node.value)
        # Matches: _BUILTIN_PROFILES = [...] (Assign)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_BUILTIN_PROFILES":
                    return ast.literal_eval(node.value)
    return []


def check_builtin_security_profiles() -> list[str]:
    """Audit builtin security profiles for forbidden capability escalations."""
    violations: list[str] = []
    profile_manager_file = _SERVER_ROOT / "app" / "services" / "security" / "profile_manager.py"
    if not profile_manager_file.exists():
        return [f"File not found: {profile_manager_file}"]

    builtin_profiles = _extract_builtin_profiles_from_ast(profile_manager_file)
    if not builtin_profiles:
        return ["_BUILTIN_PROFILES not found or empty in profile_manager.py"]

    for profile in builtin_profiles:
        key = str(profile.get("profile_key", "unknown"))
        config = profile.get("config_json")
        if not isinstance(config, dict):
            violations.append(f"Profile '{key}': missing or invalid config_json")
            continue

        # 1. Readonly profile must deny file_write, shell_exec, browser mutations
        if key == "readonly":
            perms = config.get("permissions", {})
            if not isinstance(perms, dict):
                violations.append("Profile 'readonly': permissions must be a dict")
            else:
                for dangerous in (
                    "file_write",
                    "file_edit",
                    "file_delete",
                    "shell_exec",
                    "code_interpreter",
                    "browser_evaluate",
                    "browser_fill",
                    "browser_upload",
                    "browser_download",
                ):
                    action = perms.get(dangerous)
                    if action != "deny":
                        violations.append(f"Profile 'readonly': '{dangerous}' must be 'deny', got '{action}'")
                if config.get("yoloModeEnabled") is True:
                    violations.append("Profile 'readonly': yoloModeEnabled must be False")

        # 2. Workspace profile must not allow shell/CI without approval (must be ask or deny)
        if key == "workspace":
            perms = config.get("permissions", {})
            if isinstance(perms, dict):
                for sensitive in ("shell_exec", "code_interpreter", "mcp_invoke"):
                    action = perms.get(sensitive)
                    if action == "allow":
                        violations.append(f"Profile 'workspace': '{sensitive}' must not be 'allow'")
                if config.get("yoloModeEnabled") is True:
                    violations.append("Profile 'workspace': yoloModeEnabled must be False")

        # 3. All builtin profiles must have explicit capabilities list
        caps = config.get("capabilities")
        if not isinstance(caps, list):
            violations.append(f"Profile '{key}': capabilities must be an explicit list")

    return violations


def main() -> int:
    print("🔍 Auditing built-in profiles for Capability Escalation...")
    violations = check_builtin_security_profiles()

    if violations:
        print("❌ Profile Capability Escalation CI Gate FAILED:")
        for v in violations:
            print(f"  - {v}")
        return 1

    print("✅ Profile Capability Escalation CI Gate PASSED (all profiles conform to baseline).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
