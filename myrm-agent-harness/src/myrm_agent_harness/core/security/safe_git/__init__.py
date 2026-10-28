"""Hardened git argv for the application's own, automatic git commands.

[INPUT]
- argv: HARDENED_GIT_CONFIG / HARDENED_GIT_ENV / hardened_git_argv / hardened_git_argv_async / require_own_repository (POS: the hardened argv and the check that runs before a caller writes into a repository)
- query: GitHardeningError (POS: the refusal every check raises)

[OUTPUT]
- GitHardeningError: a repository's config cannot be neutralised safely, or its layout is not its directory's own, so git must not run
- HARDENED_GIT_CONFIG: ``-c`` overrides that switch off the programs git and git-lfs take from fixed configuration keys, the network and signing
- HARDENED_GIT_ENV: environment for commands that write the tree, so a credential request fails instead of prompting
- hardened_git_argv / hardened_git_argv_async: full ``git`` argv for one command in one repository
- require_own_repository: refuse a directory no hardened command could run in

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

A folder also chooses which repository git works in, and git does not record which directory owns a git directory. A
``.git`` symlink, a ``.git`` file naming another repository, a ``commondir`` file or a ``core.worktree`` aims a command
at another repository's branches, index and files: ``commit`` then moves *that* repository's ``main``. Before any
command that touches refs, the index or the work tree, ``layout`` proves the directory's repository is its own and
refuses (``GitHardeningError``) otherwise. Accepted: a ``.git`` directory that holds the repository; a linked worktree;
a submodule checkout; a bare repository the directory sits in. A separate git directory (``git init
--separate-git-dir``) cannot be told from a hostile ``.git`` file and is refused too. The two layouts the application
itself creates (an ordinary repository, a linked worktree) are proved from files alone and add no git process.
Subcommands that only read objects never reach the work tree and skip the proof.

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

from .argv import (
    HARDENED_GIT_CONFIG,
    HARDENED_GIT_ENV,
    hardened_git_argv,
    hardened_git_argv_async,
    require_own_repository,
)
from .query import GitHardeningError

__all__ = [
    "HARDENED_GIT_CONFIG",
    "HARDENED_GIT_ENV",
    "GitHardeningError",
    "hardened_git_argv",
    "hardened_git_argv_async",
    "require_own_repository",
]
