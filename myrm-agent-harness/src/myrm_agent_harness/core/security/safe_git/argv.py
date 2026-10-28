"""Hardened git argv for the application's own, automatic git commands.

[INPUT]
- layout: lexical_layout / require_resolved_layout (POS: proof that the repository git would use is the directory's own)
- query: GitHardeningError / query_git (POS: one short ``git config`` listing per hardened command)

[OUTPUT]
- HARDENED_GIT_CONFIG: ``-c`` overrides that switch off the programs git and git-lfs take from fixed configuration keys, the network and signing
- HARDENED_GIT_ENV: environment for commands that write the tree, so a credential request fails instead of prompting
- hardened_git_argv / hardened_git_argv_async: full ``git`` argv for one command in one repository
- require_own_repository: refuse, before the caller writes anything of its own, a directory no hardened command could run in

[POS]
The argv builder of ``core.security.safe_git``: fixed overrides, per-repository program neutralisation from one
configuration listing, and the layout proof (``layout``) that runs ahead of it for every command that touches refs, the
index or the work tree. Subcommands that only read objects (``rev-parse``, ``log``, ``show``...) need neither.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from .layout import LexicalLayout, lexical_layout, require_resolved_layout
from .query import GitHardeningError, query_git

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
# What ``git lfs install`` writes (``--skip-smudge`` adds ``--skip``). git-lfs is found on the user's PATH, which a
# repository cannot change, so a repository-local filter with exactly these commands runs no program it chose.
_STANDARD_LFS_COMMANDS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "filter.lfs.clean": frozenset({"git-lfs clean -- %f"}),
        "filter.lfs.smudge": frozenset({"git-lfs smudge -- %f", "git-lfs smudge --skip -- %f"}),
        "filter.lfs.process": frozenset({"git-lfs filter-process", "git-lfs filter-process --skip"}),
    }
)
# Subcommands that only read objects, never hash a working-tree file or move a ref, so no ``filter.<name>`` driver can
# run, no work tree is reached, and neither the per-repository listing (one extra git process) nor the layout proof
# is needed. Anything not listed here pays for both.
_OBJECT_READ_SUBCOMMANDS = frozenset({"rev-parse", "rev-list", "log", "show", "cat-file", "diff-tree", "ls-tree"})
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
# git reports "no such key" (1) or "not a repository / config git itself refuses" (128): in both a following
# command either has nothing to neutralise or fails before it can run anything.
_NOTHING_TO_LIST_EXIT_CODES = frozenset({1, 128})


def _repository_overrides(
    repo_dir: str, env: Mapping[str, str] | None, *, skip_filters: bool
) -> tuple[list[str], bool]:
    """``-c`` overrides blanking every program the repository names, from one listing, and whether the repository's
    configuration sets ``core.worktree``; refuses a repository whose configuration cannot be neutralised."""
    completed = query_git(
        repo_dir,
        env,
        ("config", "--show-scope", "-z", "--get-regexp", _REPOSITORY_KEY_PATTERN),
        purpose="list repository git configuration",
    )

    if completed.returncode in _NOTHING_TO_LIST_EXIT_CODES:
        return [], False
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
    names_worktree = False
    for scope, entry in zip(fields[0::2], fields[1::2], strict=True):
        if scope not in _REPOSITORY_SCOPES:
            continue
        key, _, value = entry.partition("\n")
        if key == _WORKTREE_KEY:
            names_worktree = True
            continue
        if key.startswith(_CONDITIONAL_INCLUDE_PREFIX):
            raise GitHardeningError(f"Repository git configuration has a conditional include: {key!r}")
        if "=" in key:
            # ``-c key=value`` splits on the first ``=``, so such a name could not be blanked reliably.
            raise GitHardeningError(f"Repository git configuration key cannot be neutralised: {key!r}")
        standard[key] = standard.get(key, True) and value in _STANDARD_LFS_COMMANDS.get(key, ())

    overrides: dict[str, None] = {}
    for key, is_standard in standard.items():
        if is_standard:
            continue
        overrides[f"{key}="] = None
        if skip_filters and key.startswith("filter."):
            # A required filter with no command makes git fail instead of skipping it.
            overrides[f"{key.rsplit('.', 1)[0]}.required=false"] = None
    return list(overrides), names_worktree


def _skips_blanked_filters(args: Sequence[str]) -> bool:
    return args[0] in _RAW_CONTENT_SUBCOMMANDS or tuple(args[:2]) == ("stash", "create")


def _program_overrides(args: Sequence[str], directory: str, env: Mapping[str, str] | None) -> list[str]:
    """Overrides for a command that may touch refs, the index or the work tree, once the repository is proved the
    directory's own."""
    creates_repository = args[0] == "init" and not os.path.lexists(os.path.join(directory, ".git"))
    layout = LexicalLayout.ABSENT if creates_repository else lexical_layout(directory, env)
    if layout is LexicalLayout.FOREIGN:
        raise GitHardeningError(f"The git repository serving {directory} does not belong to that directory")
    overrides, names_worktree = _repository_overrides(directory, env, skip_filters=_skips_blanked_filters(args))
    if layout is LexicalLayout.UNKNOWN or (names_worktree and layout is not LexicalLayout.ABSENT):
        require_resolved_layout(directory, env, names_worktree=names_worktree)
    return overrides


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
    Costs one short ``git config`` query unless the subcommand only reads objects (a submodule checkout, a repository
    that sets ``core.worktree`` or a bare repository costs one ``git rev-parse`` more). Raises ``GitHardeningError``
    (an ``OSError``) when the repository's configuration cannot be neutralised or the repository is not the
    directory's own (see ``layout``), which callers already treat as "git unavailable".
    """
    if not args or args[0].startswith("-"):
        raise ValueError("args must start with a git subcommand")
    for item in config:
        key, separator, _ = item.partition("=")
        if not separator or key in _HARDENED_KEYS:
            raise ValueError(f"config must be a key=value that is not hardened: {item!r}")
    directory = os.path.realpath(os.fspath(repo_dir))
    program_overrides = [] if args[0] in _OBJECT_READ_SUBCOMMANDS else _program_overrides(args, directory, env)
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


def require_own_repository(repo_dir: str | os.PathLike[str], *, env: Mapping[str, str] | None = None) -> None:
    """Raise ``GitHardeningError`` unless a command that touches the work tree could run in *repo_dir*.

    The verdict ``hardened_git_argv`` gives a ``status``, for a caller that must know before it writes anything of its
    own into the directory. A directory with no repository passes: git then fails by itself.
    """
    hardened_git_argv(("status",), repo_dir=repo_dir, env=env)
