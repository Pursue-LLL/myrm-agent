"""Hardened git argv for the application's own, automatic git commands.

[INPUT]
- subprocess::run (POS: one short ``git config`` listing per hardened command, and a ``git rev-parse`` for a repository that names a work tree)

[OUTPUT]
- GitHardeningError: a repository's config cannot be neutralised safely, or sends git to work somewhere else, so git must not run
- HARDENED_GIT_CONFIG: ``-c`` overrides that switch off the programs git and git-lfs take from fixed configuration keys, the network and signing
- HARDENED_GIT_ENV: environment for commands that write the tree, so a credential request fails instead of prompting
- hardened_git_argv / hardened_git_argv_async: full ``git`` argv for one command in one repository

[POS]
Foundation security primitive. A repository chooses programs git runs during ordinary commands —
``core.fsmonitor``, ``diff.external``, ``diff.<driver>.textconv|command``, ``filter.<name>.*``,
``merge.<name>.driver`` and, through git-lfs, credential helpers, ``core.askPass``, ``core.sshCommand``,
``lfs.extension.<name>.*`` and ``lfs.customtransfer.<name>.path`` — so a folder that arrives with its ``.git``
directory can execute code the moment the application inspects or updates it, outside every sandbox and approval.
Calls the application starts itself on a user- or agent-controlled working tree go through this argv; commands the
user or agent types are governed by the sandbox and approvals instead, and a user's own global and system
configuration is left alone.

Fixed keys are blanked with ``-c``; the ``filter.<name>``, ``merge.<name>``, ``lfs.extension.<name>`` and
``lfs.customtransfer.<name>`` programs a repository names are listed and blanked too. A repository-local
``includeIf`` is refused: git evaluates its condition again in every child process (for instance on a branch the
command is about to create), so no listing can know which file it will pull in. Every git transport is refused, so an
object a partial clone lacks is an error instead of a fetch. (``GIT_ALLOW_PROTOCOL``, if the operator exports it,
takes precedence over configuration.) External diff and textconv cannot be blanked (git then fails with "cannot
run"), so the patch-producing subcommands carry ``--no-ext-diff --no-textconv`` instead. ``status`` and ``diff`` also
stop descending into submodules' working trees: git runs a child ``status`` there that honours the submodule's own,
separately stored configuration, which no override of the parent's listing can reach (``submodule.recurse=false``
does the same for the commands that update a tree). The listing is one extra git process, so subcommands that only
read objects (``rev-parse``, ``log``, ``show``…) skip it.

A repository also chooses where git works. A ``core.worktree`` that names a directory the repository does not own
makes ``checkout``, ``merge``, ``reset`` or ``add`` write into, or read from, that directory instead of the folder the
caller passed. The same listing finds the key, and it is accepted only when ``<work tree>/.git`` leads back to the git
directory in use (a submodule's checkout does); anything else is refused. A ``.git`` that is a file or a symlink, or a
``commondir`` file, aims a repository at another git directory too, but linked worktrees and submodules are built
exactly that way, so this primitive accepts them: a caller that adopts a folder as its own repository checks that the
layout is its own (``vault_git`` does).

A filter that is switched off does not transform content (an LFS pointer, an encrypted blob). Commands whose result
stays private or is raw by design (``status``, ``diff``, ``ls-files``, ``stash create``, and ``read-tree``, which puts
back what ``stash create`` recorded) declare such a filter not required, so git carries on with the raw content. Every
other command keeps the repository's own ``required`` flag: git then fails instead of committing or checking out
content the filter would have transformed. A repository-local ``filter.lfs`` whose commands are exactly what
``git lfs install`` writes is left active, because git-lfs is found on the user's PATH, which a repository cannot
change.

git-lfs is a separate program with its own transport, which ``protocol.<name>.allow`` does not govern: when an LFS
object is missing locally it contacts the host the repository names. ``credential.helper``, ``core.askPass``,
``core.sshCommand`` and ``lfs.standalonetransferagent`` are neutralised, so no program starts and the user's
credential store is never asked (``core.sshCommand`` is ``false`` and not empty: an empty value makes git-lfs start
the ``ssh`` found on PATH), and ``HARDENED_GIT_ENV`` makes git fail instead of prompting on a terminal. What remains
is one unauthenticated request to a host the repository names. ``GIT_LFS_SKIP_SMUDGE`` is deliberately not set: it
also replaces content git-lfs already holds locally with pointer files.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Mapping, Sequence
from types import MappingProxyType

__all__ = [
    "HARDENED_GIT_CONFIG",
    "HARDENED_GIT_ENV",
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
    # git-lfs reads the repository's settings itself, so ``protocol.<name>.allow`` does not reach it. An empty
    # ``credential.helper`` drops every helper configured so far, ``credential.<url>.helper`` included.
    # ``core.sshCommand`` is ``false``, not empty: an empty value makes git-lfs start the ``ssh`` found on PATH.
    "credential.helper=",
    "core.askPass=",
    "core.sshCommand=false",
    "lfs.standalonetransferagent=",
    # A submodule's own configuration is stored apart; no override of the parent's listing can reach it.
    "submodule.recurse=false",
)
_HARDENED_KEYS = frozenset(item.partition("=")[0] for item in HARDENED_GIT_CONFIG)

# A command that writes the tree can make git-lfs ask for credentials; with a controlling terminal that request would
# become a prompt that stalls the command.
HARDENED_GIT_ENV: Mapping[str, str] = MappingProxyType({"GIT_TERMINAL_PROMPT": "0"})

# Keys the repository controls that one listing must find: per-name program keys (the names are chosen by the
# repository, so they are listed, not hard-coded), ``includeif`` (listed to be refused: git evaluates its condition
# again in every child process) and ``core.worktree`` (not a program; it rides in the same listing so a repository that
# does not set it pays nothing more).
_REPOSITORY_KEY_PATTERN = (
    r"^(filter\..+\.(clean|smudge|process)|merge\..+\.driver"
    r"|lfs\.extension\..+\.(clean|smudge)|lfs\.customtransfer\..+\.path|includeif\..+\.path|core\.worktree)$"
)
_CONDITIONAL_INCLUDE_PREFIX = "includeif."
_WORKTREE_KEY = "core.worktree"
_GITFILE_PREFIX = "gitdir:"
_GITFILE_MAX_BYTES = 4096
# What ``git lfs install`` writes (``--skip-smudge`` adds ``--skip``). git-lfs is found on the user's PATH, which a
# repository cannot change, so a repository-local filter with exactly these commands runs no program it chose.
_STANDARD_LFS_COMMANDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "filter.lfs.clean": frozenset({"git-lfs clean -- %f"}),
        "filter.lfs.smudge": frozenset({"git-lfs smudge -- %f", "git-lfs smudge --skip -- %f"}),
        "filter.lfs.process": frozenset({"git-lfs filter-process", "git-lfs filter-process --skip"}),
    }
)
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


def _query_git(
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


def _leads_back_to(dot_git: str, git_dir: str) -> bool:
    """Whether ``dot_git`` is the git directory itself or a file that names it (a submodule's or worktree's pointer)."""
    try:
        if os.path.isdir(dot_git):
            return os.path.samefile(dot_git, git_dir)
        with open(dot_git, "rb") as handle:
            first_line = os.fsdecode(handle.read(_GITFILE_MAX_BYTES)).split("\n", 1)[0].strip()
        if not first_line.startswith(_GITFILE_PREFIX):
            return False
        target = first_line[len(_GITFILE_PREFIX) :].strip()
        return os.path.samefile(os.path.join(os.path.dirname(dot_git), target), git_dir)
    except OSError:
        return False


def _require_owned_worktree(repo_dir: str, env: Mapping[str, str] | None) -> None:
    """Refuse a ``core.worktree`` whose directory does not point back at this repository's git directory."""
    completed = _query_git(
        repo_dir,
        env,
        ("rev-parse", "--show-toplevel", "--absolute-git-dir"),
        purpose="locate the repository's work tree",
    )
    lines = completed.stdout.decode("utf-8", "surrogateescape").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if completed.returncode != 0 or len(lines) != 2:
        raise GitHardeningError(f"Cannot locate the work tree of the repository in {repo_dir}")
    worktree, git_dir = lines
    if not _leads_back_to(os.path.join(worktree, ".git"), git_dir):
        raise GitHardeningError(f"Repository git configuration sends git to a work tree it does not own: {worktree!r}")


def _repository_overrides(repo_dir: str, env: Mapping[str, str] | None, *, skip_filters: bool) -> list[str]:
    """``-c`` overrides blanking every program the repository names, from one listing; refuses a repository whose
    configuration cannot be neutralised or sends git to a work tree it does not own."""
    completed = _query_git(
        repo_dir,
        env,
        ("config", "--show-scope", "-z", "--get-regexp", _REPOSITORY_KEY_PATTERN),
        purpose="list repository git configuration",
    )

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

    # key -> whether every occurrence is a standard LFS command (git uses the last occurrence, so one other is enough)
    standard: dict[str, bool] = {}
    redirected = False
    for scope, entry in zip(fields[0::2], fields[1::2], strict=True):
        if scope not in _REPOSITORY_SCOPES:
            continue
        key, _, value = entry.partition("\n")
        if key == _WORKTREE_KEY:
            redirected = True
            continue
        if key.startswith(_CONDITIONAL_INCLUDE_PREFIX):
            raise GitHardeningError(f"Repository git configuration has a conditional include: {key!r}")
        if "=" in key:
            # ``-c key=value`` splits on the first ``=``, so such a name could not be blanked reliably.
            raise GitHardeningError(f"Repository git configuration key cannot be neutralised: {key!r}")
        standard[key] = standard.get(key, True) and value in _STANDARD_LFS_COMMANDS.get(key, ())

    if redirected:
        _require_owned_worktree(repo_dir, env)

    overrides: dict[str, None] = {}
    for key, is_standard in standard.items():
        if is_standard:
            continue
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
        else _repository_overrides(directory, env, skip_filters=_skips_blanked_filters(args))
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
