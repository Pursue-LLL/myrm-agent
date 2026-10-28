"""Read local wiki vault git status for Settings stats.

[INPUT]
myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure
myrm_agent_harness.toolkits.wiki.core.config::WikiConfig
myrm_agent_harness.api.security::hardened_git_argv / require_own_repository / GitHardeningError (POS: git argv that runs no program the repository chose, and the proof that the vault's repository is its own)

[OUTPUT]
VaultGitStatus: enabled/initialized/last commit summary for /wiki/stats; a vault whose repository is not its own reports not initialized, as no snapshot is ever taken there

[POS]
Server-only vault git UX signals (Local/Tauri). No agent prompt impact.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

from myrm_agent_harness.api.security import GitHardeningError, hardened_git_argv, require_own_repository
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure


@dataclass(frozen=True, slots=True)
class VaultGitStatus:
    enabled: bool
    initialized: bool
    last_commit: str | None = None


def read_vault_git_status(structure: WikiStructure, config: WikiConfig) -> VaultGitStatus:
    """Return vault git visibility fields for Settings when version control is enabled."""
    if not config.enable_version_control:
        return VaultGitStatus(enabled=False, initialized=False, last_commit=None)

    if shutil.which("git") is None:
        return VaultGitStatus(enabled=True, initialized=False, last_commit=None)

    vault_dir = structure.base_dir.resolve()
    if not os.path.lexists(vault_dir / ".git"):
        return VaultGitStatus(enabled=True, initialized=False, last_commit=None)

    try:
        require_own_repository(vault_dir)
    except GitHardeningError:
        return VaultGitStatus(enabled=True, initialized=False, last_commit=None)

    try:
        proc = subprocess.run(
            hardened_git_argv(("log", "-1", "--format=%h %s"), repo_dir=vault_dir),
            capture_output=True,
            text=True,
            check=True,
        )
        summary = proc.stdout.strip() or None
        return VaultGitStatus(enabled=True, initialized=True, last_commit=summary)
    except subprocess.CalledProcessError:
        return VaultGitStatus(enabled=True, initialized=True, last_commit=None)
