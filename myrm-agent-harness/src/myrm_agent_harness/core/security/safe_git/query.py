"""One read-only ``git`` query for the hardening checks, and the error they raise.

[INPUT]
- subprocess::run (POS: the short ``git config`` and ``git rev-parse`` queries run before a hardened command)

[OUTPUT]
- GitHardeningError: a repository's config cannot be neutralised safely, or its layout is not its directory's own, so git must not run
- query_git: run one read-only git query; a git that cannot be started or answered in time refuses the command

[POS]
Leaf of ``core.security.safe_git`` with no import from its siblings, so ``argv`` and ``layout`` both use it.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence

_QUERY_TIMEOUT_SECONDS = 5.0


class GitHardeningError(OSError):
    """The repository's configuration or layout cannot be trusted, so no git command may run in it."""


def query_git(
    repo_dir: str, env: Mapping[str, str] | None, args: Sequence[str], *, purpose: str
) -> subprocess.CompletedProcess[bytes]:
    """One read-only ``git`` query; a git that cannot even be started or answered in time refuses the command."""
    try:
        return subprocess.run(
            ["git", "-C", repo_dir, *args],
            capture_output=True,
            timeout=_QUERY_TIMEOUT_SECONDS,
            check=False,
            env=None if env is None else dict(env),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitHardeningError(f"Cannot {purpose} in {repo_dir}: {exc}") from exc
