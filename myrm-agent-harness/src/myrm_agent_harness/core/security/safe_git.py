"""Hardened git argv for the application's own, automatic git reads.

[INPUT]
- subprocess::run (POS: one short ``git config`` query per hardened command)

[OUTPUT]
- GitHardeningError: a repository's config cannot be neutralised safely, so git must not run
- HARDENED_GIT_CONFIG: ``-c`` overrides that switch off the programs git takes from fixed configuration keys
- hardened_git_argv / hardened_git_argv_async: full ``git`` argv for one inspection command in one repository

[POS]
Foundation security primitive. A repository chooses programs git runs during an ordinary ``status`` / ``diff`` /
``ls-files`` — ``core.fsmonitor``, ``diff.external``, ``diff.<driver>.textconv|command``, ``filter.<name>.*`` —
so a folder that arrives with its ``.git`` directory can execute code the moment the application inspects it, outside
every sandbox and approval. Calls the application starts itself on a user- or agent-controlled working tree go
through this argv; commands the user or agent types are governed by the sandbox and approvals instead, and a
user's own global and system configuration is left alone.

Fixed keys are blanked with ``-c``; the repository-named ``filter.<name>`` drivers are listed and blanked too.
External diff and textconv cannot be blanked (git then fails with "cannot run"), so the patch-producing
subcommands carry ``--no-ext-diff --no-textconv`` instead. ``status`` and ``diff`` also stop descending into
submodules' working trees: git runs a child ``status`` there that honours the submodule's own, separately stored
configuration, which no override of the parent's listing can reach.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Mapping, Sequence

__all__ = [
    "HARDENED_GIT_CONFIG",
    "GitHardeningError",
    "hardened_git_argv",
    "hardened_git_argv_async",
]

# Empty values, not ``false``: git before 2.35.2 reads ``core.fsmonitor=false`` as the name of a hook.
HARDENED_GIT_CONFIG: tuple[str, ...] = (
    "core.fsmonitor=",
    f"core.hooksPath={os.devnull}",
    "gpg.program=",
    "gpg.ssh.program=",
    "gpg.x509.program=",
)

# Per-driver program keys: the driver names are chosen by the repository, so they are listed, not hard-coded.
_FILTER_KEY_PATTERN = r"^filter\..+\.(clean|smudge|process)$"
_NO_DIFF_PROGRAMS = ("--no-ext-diff", "--no-textconv")
# Flags placed ahead of the caller's own arguments, per subcommand. ``dirty`` keeps reporting a submodule whose
# recorded commit changed and skips only its working-tree inspection.
_SUBCOMMAND_FLAGS: Mapping[str, tuple[str, ...]] = {
    "diff": (*_NO_DIFF_PROGRAMS, "--ignore-submodules=dirty"),
    "log": _NO_DIFF_PROGRAMS,
    "show": _NO_DIFF_PROGRAMS,
    "status": ("--ignore-submodules=dirty",),
}
# Scopes whose files travel with the folder; global and system configuration belongs to the user.
_REPOSITORY_SCOPES = frozenset({"local", "worktree"})
_QUERY_TIMEOUT_SECONDS = 5.0
# git reports "no such key" (1) or "not a repository / config git itself refuses" (128): in both a following
# command either has nothing to neutralise or fails before it can run anything.
_NOTHING_TO_LIST_EXIT_CODES = frozenset({1, 128})


class GitHardeningError(OSError):
    """The repository's configuration cannot be neutralised safely, so no git command may run in it."""


def _repository_filter_overrides(repo_dir: str, env: Mapping[str, str] | None) -> list[str]:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                repo_dir,
                "config",
                "--show-scope",
                "--name-only",
                "-z",
                "--get-regexp",
                _FILTER_KEY_PATTERN,
            ],
            capture_output=True,
            timeout=_QUERY_TIMEOUT_SECONDS,
            check=False,
            env=None if env is None else dict(env),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitHardeningError(f"Cannot list repository git configuration in {repo_dir}: {exc}") from exc

    if completed.returncode in _NOTHING_TO_LIST_EXIT_CODES:
        return []
    if completed.returncode != 0:
        raise GitHardeningError(
            f"Cannot list repository git configuration in {repo_dir}: git exited with {completed.returncode}"
        )

    fields = completed.stdout.decode("utf-8", "surrogateescape").split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) % 2:
        raise GitHardeningError(f"Unexpected git configuration listing in {repo_dir}")

    overrides: dict[str, None] = {}
    for scope, key in zip(fields[0::2], fields[1::2], strict=True):
        if scope not in _REPOSITORY_SCOPES:
            continue
        if "=" in key or "\n" in key:
            # ``-c key=value`` splits on the first ``=``, so such a name could not be blanked reliably.
            raise GitHardeningError(f"Repository git configuration key cannot be neutralised: {key!r}")
        overrides[f"{key}="] = None
        if key.startswith("filter."):
            # A required filter with no command makes git fail instead of skipping it.
            overrides[f"{key.rsplit('.', 1)[0]}.required=false"] = None
    return list(overrides)


def hardened_git_argv(
    args: Sequence[str],
    *,
    repo_dir: str | os.PathLike[str],
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Full ``git`` argv running *args* (a subcommand and its arguments) in *repo_dir* with every repository-selected
    program switched off.

    Costs one short ``git config`` query. Raises ``GitHardeningError`` (an ``OSError``) when the repository's
    configuration cannot be neutralised, which callers already treat as "git unavailable".
    """
    if not args or args[0].startswith("-"):
        raise ValueError("args must start with a git subcommand")
    directory = os.path.realpath(os.fspath(repo_dir))
    overrides = (*HARDENED_GIT_CONFIG, *_repository_filter_overrides(directory, env))
    argv = ["git"]
    for override in overrides:
        argv.extend(("-c", override))
    argv.extend(("-C", directory))
    argv.append(args[0])
    argv.extend(_SUBCOMMAND_FLAGS.get(args[0], ()))
    argv.extend(args[1:])
    return argv


async def hardened_git_argv_async(
    args: Sequence[str],
    *,
    repo_dir: str | os.PathLike[str],
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """``hardened_git_argv`` without blocking the event loop."""
    return await asyncio.to_thread(hardened_git_argv, args, repo_dir=repo_dir, env=env)
