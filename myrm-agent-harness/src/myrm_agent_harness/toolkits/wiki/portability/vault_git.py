"""Local git auto-commit for wiki vault directories.

[INPUT]
- myrm_agent_harness.core.security.safe_git::hardened_git_argv (POS: git argv that runs no program the repository chose)
- myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure (POS: vault layout)
- myrm_agent_harness.toolkits.wiki.core.config::WikiConfig (POS: version control knobs)

[OUTPUT]
- commit_vault_git_snapshot: Initialize repo if needed and commit vault changes; skipped_reason ``unsafe_repository``
  when the vault's git configuration cannot be neutralised or its repository is not the vault's own
- maybe_commit_vault_git_snapshot: Gate on WikiConfig.enable_version_control

[POS]
Framework-level vault version discipline for Karpathy/Obsidian users who expect git log/blame.
Uses a real .git inside the vault base_dir (not shadow git). That ``.git``, and any repository nested below the vault
root, may have arrived as plain files (a ZIP, a sync folder, a restored backup), so every command goes through
``hardened_git_argv``: the programs their configuration names (fsmonitor, hooks, filters) do not run during a snapshot.
The vault also commits only into a repository of its own: ``.git`` must be a real directory inside the vault and git's
top level, git directory and common directory must all be that directory, so a ``.git`` file or symlink, a
``commondir`` file or a ``core.worktree`` cannot make a snapshot land on another repository's branch or read another
folder's files. A vault laid out differently (a separate git directory, a linked worktree) is skipped, not adopted.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.core.security.safe_git import HARDENED_GIT_ENV, GitHardeningError, hardened_git_argv
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)

_VAULT_GITIGNORE = """# Myrm wiki vault — auto-managed
**/.metadata.json
wiki/.metadata.json
*.sqlite
*.sqlite3
*.db
__pycache__/
.DS_Store
Thumbs.db
"""

_GIT_AUTHOR_NAME = "Myrm"
_GIT_AUTHOR_EMAIL = "myrm@local"


@dataclass(frozen=True, slots=True)
class VaultGitCommitResult:
    committed: bool
    commit_hash: str | None = None
    skipped_reason: str | None = None


def _run_git(vault_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run git in the vault without any program its configuration names; ``GitHardeningError`` if that is impossible."""
    env = {**os.environ, **HARDENED_GIT_ENV}
    return subprocess.run(
        hardened_git_argv(args, repo_dir=vault_dir, env=env),
        capture_output=True,
        text=True,
        check=check,
        env=env,
    )


def _git_available() -> bool:
    return shutil.which("git") is not None


def _same_path(vault_dir: Path, reported: str, expected: Path) -> bool:
    """``reported`` is what git printed from inside the vault, so a relative one (``.git``) is relative to the vault."""
    try:
        return os.path.samefile(vault_dir / reported, expected)
    except OSError:
        return False


def _require_own_repository(vault_dir: Path) -> None:
    """``.git`` is a real directory inside the vault and git itself reports that directory as every root it uses."""
    git_dir = vault_dir / ".git"
    reported = _run_git(
        vault_dir, "rev-parse", "--show-toplevel", "--absolute-git-dir", "--git-common-dir"
    ).stdout.split("\n")
    if reported and reported[-1] == "":
        reported.pop()
    expected = (vault_dir, git_dir, git_dir)
    if len(reported) != len(expected) or not all(
        _same_path(vault_dir, got, want) for got, want in zip(reported, expected, strict=True)
    ):
        raise GitHardeningError(f"The vault's git repository is not its own: {reported!r}")


def _ensure_repo(vault_dir: Path) -> None:
    git_dir = vault_dir / ".git"
    if git_dir.is_symlink() or (git_dir.exists() and not git_dir.is_dir()):
        raise GitHardeningError(f"The vault's .git is not a plain directory: {git_dir}")
    if not git_dir.exists():
        _run_git(vault_dir, "init", "--initial-branch=main")
        _run_git(vault_dir, "config", "user.name", _GIT_AUTHOR_NAME)
        _run_git(vault_dir, "config", "user.email", _GIT_AUTHOR_EMAIL)
    _require_own_repository(vault_dir)

    gitignore_path = vault_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(_VAULT_GITIGNORE, encoding="utf-8")


def _has_staged_changes(vault_dir: Path) -> bool:
    head = _run_git(vault_dir, "rev-parse", "--verify", "HEAD", check=False)
    if head.returncode != 0:
        status = _run_git(vault_dir, "status", "--porcelain")
        return bool(status.stdout.strip())
    diff = _run_git(vault_dir, "diff-index", "--cached", "--quiet", "HEAD", check=False)
    return diff.returncode != 0


def commit_vault_git_snapshot(
    structure: WikiStructure,
    *,
    reason: str,
) -> VaultGitCommitResult:
    """Commit current vault tree when git is available and files changed.

    A vault whose git configuration cannot be neutralised (a conditional include) or whose repository is not its own
    (see the module docstring) is skipped, never committed to.
    """
    if not _git_available():
        return VaultGitCommitResult(committed=False, skipped_reason="git_unavailable")

    vault_dir = structure.base_dir.resolve()
    if not vault_dir.is_dir():
        return VaultGitCommitResult(committed=False, skipped_reason="vault_missing")

    try:
        _ensure_repo(vault_dir)
        _run_git(vault_dir, "add", "-A")
        if not _has_staged_changes(vault_dir):
            return VaultGitCommitResult(committed=False, skipped_reason="no_changes")

        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        message = f"myrm: {reason}\n\ntimestamp={timestamp}"
        _run_git(vault_dir, "commit", "-m", message, "--no-gpg-sign", "--no-verify")
        rev = _run_git(vault_dir, "rev-parse", "HEAD")
        commit_hash = rev.stdout.strip()
        logger.info("Wiki vault git snapshot committed (%s): %s", reason, commit_hash)
        return VaultGitCommitResult(committed=True, commit_hash=commit_hash)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or "").strip()
        logger.warning("Wiki vault git snapshot failed (%s): %s", reason, stderr)
        return VaultGitCommitResult(committed=False, skipped_reason="git_error")
    except GitHardeningError as exc:
        logger.warning("Wiki vault git snapshot skipped (%s): %s", reason, exc)
        return VaultGitCommitResult(committed=False, skipped_reason="unsafe_repository")


def maybe_commit_vault_git_snapshot(
    structure: WikiStructure,
    config: WikiConfig,
    *,
    reason: str,
) -> VaultGitCommitResult:
    """Commit vault snapshot when version control is enabled in WikiConfig."""
    if not config.enable_version_control:
        return VaultGitCommitResult(committed=False, skipped_reason="disabled")
    return commit_vault_git_snapshot(structure, reason=reason)
