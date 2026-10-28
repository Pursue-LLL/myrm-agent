"""Hardened git argv for the application's own, automatic git commands.

[INPUT]
- subprocess::run (POS: one short ``git config`` query per hardened command)

[OUTPUT]
- GitHardeningError: a repository's config cannot be neutralised safely, so git must not run
- HARDENED_GIT_CONFIG: ``-c`` overrides that switch off the programs git takes from fixed configuration keys, the network and signing
- hardened_git_argv / hardened_git_argv_async: full ``git`` argv for one command in one repository

[POS]
Foundation security primitive. A repository chooses programs git runs during ordinary commands —
``core.fsmonitor``, ``diff.external``, ``diff.<driver>.textconv|command``, ``filter.<name>.*``,
``merge.<name>.driver``, and, whenever an object is missing from a partial clone, the remote's
``uploadpack`` or ``core.sshCommand`` — so a folder that arrives with its ``.git`` directory can execute code the
moment the application inspects or updates it, outside every sandbox and approval. Calls the application starts
itself on a user- or agent-controlled working tree go through this argv; commands the user or agent types are
governed by the sandbox and approvals instead, and a user's own global and system configuration is left alone.

Fixed keys are blanked with ``-c``; the repository-named ``filter.<name>`` and ``merge.<name>`` drivers are listed and
blanked too. Every transport is refused, so an object a partial clone lacks is an error instead of a fetch.
(``GIT_ALLOW_PROTOCOL``, if the operator exports it, takes precedence over configuration.) External diff and
textconv cannot be blanked (git then fails with "cannot run"), so the patch-producing subcommands carry
``--no-ext-diff --no-textconv`` instead. ``status`` and ``diff`` also stop descending into submodules' working trees:
git runs a child ``status`` there that honours the submodule's own, separately stored configuration, which no
override of the parent's listing can reach. The listing is one extra git process, so subcommands that only read
objects (``rev-parse``, ``log``, ``show``…) skip it.

A filter that is switched off does not transform content (an LFS pointer, an encrypted blob). Commands whose result
stays private or is raw by design (``status``, ``diff``, ``ls-files``, ``stash create``, and ``read-tree``, which puts
back what ``stash create`` recorded) declare such a filter not required, so git carries on with the raw content. Every
other command keeps the repository's own ``required`` flag: git then fails instead of committing or checking out
content the filter would have transformed.

Out of reach: a program that git starts and that then reads the repository's own settings. git-lfs does — a
repository-local ``lfs.extension.<name>.clean``, ``lfs.standalonetransferagent`` / ``lfs.customtransfer.<name>.path``
and ``lfs.url`` make it run a program or connect to a host that the repository names, and the ``-c`` overrides here
(which are for git's own keys) do not stop it. Only a machine with git-lfs installed is exposed.
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

_TRANSPORTS = ("file", "ssh", "http", "https", "git", "ext")

# Empty values, not ``false``: git before 2.35.2 reads ``core.fsmonitor=false`` as the name of a hook. A transport
# policy is set per transport because a repository's own ``protocol.<name>.allow`` outranks ``protocol.allow``.
HARDENED_GIT_CONFIG: tuple[str, ...] = (
    "core.fsmonitor=",
    f"core.hooksPath={os.devnull}",
    "gpg.program=",
    "gpg.ssh.program=",
    "gpg.x509.program=",
    "commit.gpgsign=false",
    *(f"protocol.{transport}.allow=never" for transport in _TRANSPORTS),
)
_HARDENED_KEYS = frozenset(item.partition("=")[0] for item in HARDENED_GIT_CONFIG)

# Per-driver program keys: the driver names are chosen by the repository, so they are listed, not hard-coded.
_PROGRAM_KEY_PATTERN = r"^(filter\..+\.(clean|smudge|process)|merge\..+\.driver)$"
# Subcommands that only read objects, never hash a working-tree file, so no ``filter.<name>`` driver can run and the
# per-repository listing (one extra git process) is skipped. Anything not listed here pays for the listing.
_FILTER_FREE_SUBCOMMANDS = frozenset({"rev-parse", "rev-list", "log", "show", "cat-file", "diff-tree", "ls-tree"})
# Subcommands whose result never enters history and writes nothing a filter should have transformed, so a blanked
# filter may be skipped. ``read-tree`` restores a ``stash create`` snapshot, whose blobs were hashed raw the same way.
_RAW_CONTENT_SUBCOMMANDS = frozenset({"status", "diff", "ls-files", "read-tree"})
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


def _repository_program_overrides(repo_dir: str, env: Mapping[str, str] | None, *, skip_filters: bool) -> list[str]:
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
                _PROGRAM_KEY_PATTERN,
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
        if skip_filters and key.startswith("filter."):
            # A required filter with no command makes git fail instead of skipping it.
            overrides[f"{key.rsplit('.', 1)[0]}.required=false"] = None
    return list(overrides)


def _skips_blanked_filters(args: Sequence[str]) -> bool:
    return args[0] in _RAW_CONTENT_SUBCOMMANDS or tuple(args[:2]) == ("stash", "create")


def hardened_git_argv(
    args: Sequence[str],
    *,
    repo_dir: str | os.PathLike[str],
    env: Mapping[str, str] | None = None,
    config: Sequence[str] = (),
) -> list[str]:
    """Full ``git`` argv running *args* (a subcommand and its arguments) in *repo_dir* with every repository-selected
    program and every transport switched off.

    *config* carries the caller's own ``key=value`` settings (a commit identity); it cannot override a hardened key.
    Costs one short ``git config`` query unless the subcommand only reads objects. Raises ``GitHardeningError`` (an
    ``OSError``) when the repository's configuration cannot be neutralised, which callers already treat as "git
    unavailable".
    """
    if not args or args[0].startswith("-"):
        raise ValueError("args must start with a git subcommand")
    for item in config:
        key, separator, _ = item.partition("=")
        if not separator or key in _HARDENED_KEYS:
            raise ValueError(f"config must be a key=value that is not hardened: {item!r}")
    directory = os.path.realpath(os.fspath(repo_dir))
    program_overrides = (
        []
        if args[0] in _FILTER_FREE_SUBCOMMANDS
        else _repository_program_overrides(directory, env, skip_filters=_skips_blanked_filters(args))
    )
    argv = ["git"]
    for override in (*HARDENED_GIT_CONFIG, *program_overrides, *config):
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
    config: Sequence[str] = (),
) -> list[str]:
    """``hardened_git_argv`` without blocking the event loop."""
    return await asyncio.to_thread(hardened_git_argv, args, repo_dir=repo_dir, env=env, config=config)
