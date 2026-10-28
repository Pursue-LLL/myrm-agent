"""A git command that reads or writes the index, the working tree or a ref goes through the hardened argv, or is listed here with why.

[INPUT]
- src/myrm_agent_harness/**/*.py: every ``git`` argv written as a list literal or as the first argument of a spawn call

[OUTPUT]
- Fails when a command that touches the tree, a ref or an object is spawned with a bare ``git`` argv and is not listed
  below with its reason, or when a listed site no longer exists (so the list cannot rot).

[POS]
Architecture guard for ``core.security.safe_git``: a repository's own config can pick programs that git runs during
``status`` / ``diff`` / ``ls-files``, so a new inspection call written the plain way would reopen that route.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4] / "src"

# Subcommands that read or write the index, the working tree or a ref, or can fetch an object: where git consults
# repository-chosen programs (a ref update runs the repository's ``reference-transaction`` hook).
_RUNS_REPOSITORY_PROGRAMS = frozenset(
    {
        "status",
        "diff",
        "diff-index",
        "diff-files",
        "ls-files",
        "stash",
        "add",
        "commit",
        "merge",
        "rebase",
        "checkout",
        "checkout-index",
        "read-tree",
        "worktree",
        "cherry-pick",
        "pull",
        "reset",
        "clean",
        "switch",
        "restore",
        "apply",
        "am",
        "revert",
        "mv",
        "rm",
        "branch",
        "tag",
        "update-ref",
        "pack-refs",
        "gc",
        # Reading history can fetch a missing object from a partial clone's remote, through a program its config names.
        "show",
        "log",
        "cat-file",
        "diff-tree",
        "blame",
        "grep",
        "archive",
    }
)
_DYNAMIC = "*"
_SPAWN_CALLS = frozenset({"run", "Popen", "check_output", "check_call", "create_subprocess_exec", "_run_cmd"})

# path under src/ -> (subcommands spawned bare there, why that is correct)
_BARE_GIT_SITES: dict[str, tuple[frozenset[str], str]] = {
    "myrm_agent_harness/core/security/safe_git.py": (
        frozenset({_DYNAMIC}),
        "builds the hardened argv itself",
    ),
    "myrm_agent_harness/agent/file_snapshot/factory.py": (
        frozenset({_DYNAMIC}),
        "`git --version` availability probe: reads no repository",
    ),
    "myrm_agent_harness/agent/file_snapshot/shadow_git_store.py": (
        frozenset(
            {_DYNAMIC, "add", "diff-index", "diff-tree", "log", "read-tree", "checkout-index", "checkout", "update-ref"}
        ),
        "runs against the snapshot store's own bare repository (GIT_DIR points at it), so the workspace's `.git/config` "
        "is never read",
    ),
    "myrm_agent_harness/agent/file_snapshot/shadow_git_maintenance.py": (
        frozenset({"ls-files", "rm", "update-ref"}),
        "same snapshot store: its own bare repository",
    ),
    "myrm_agent_harness/toolkits/wiki/portability/vault_git.py": (
        frozenset({_DYNAMIC}),
        "KNOWN GAP, not a safe site: the vault commit flow adopts an existing `.git` (`_ensure_repo` only inits when it is "
        "absent), so a vault delivered with its own `.git` runs the programs it names on add/commit (measured: fsmonitor, "
        "post-commit and reference-transaction ran)",
    ),
}


def _is_git(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == "git"


def _subcommand(items: list[ast.expr]) -> str:
    """First word that is neither a global option nor an option's value; ``*`` when it is not a literal."""
    skip_value = False
    for item in items:
        if skip_value:
            skip_value = False
            continue
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            if item.value in {"-C", "-c"}:
                skip_value = True
            elif not item.value.startswith("-"):
                return item.value
    return _DYNAMIC


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def bare_git_spawns(source: str) -> Iterator[tuple[int, str]]:
    """``(line, subcommand)`` for each git argv in *source* that is not built by ``hardened_git_argv``."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.List) and node.elts and _is_git(node.elts[0]):
            yield node.lineno, _subcommand(node.elts[1:])
        elif isinstance(node, ast.Call) and _call_name(node) in _SPAWN_CALLS and node.args and _is_git(node.args[0]):
            yield node.lineno, _subcommand(node.args[1:])


def _found() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(_SRC.rglob("*.py")):
        for _line, subcommand in bare_git_spawns(path.read_text(encoding="utf-8")):
            found.setdefault(path.relative_to(_SRC).as_posix(), set()).add(subcommand)
    return found


def test_every_tree_touching_bare_git_spawn_is_listed_with_its_reason() -> None:
    unlisted = [
        f"{path}: git {subcommand}"
        for path, subcommands in _found().items()
        for subcommand in sorted(subcommands)
        if (subcommand in _RUNS_REPOSITORY_PROGRAMS or subcommand == _DYNAMIC)
        and subcommand not in _BARE_GIT_SITES.get(path, (frozenset(), ""))[0]
    ]

    assert not unlisted, (
        "build these with core.security.safe_git.hardened_git_argv, or list them in _BARE_GIT_SITES with why:\n"
        + "\n".join(unlisted)
    )


def test_every_listed_site_still_exists() -> None:
    found = _found()
    stale = [
        f"{path}: git {subcommand}"
        for path, (subcommands, _why) in _BARE_GIT_SITES.items()
        for subcommand in sorted(subcommands)
        if subcommand not in found.get(path, set())
    ]

    assert not stale, "remove these from _BARE_GIT_SITES:\n" + "\n".join(stale)


class TestTheScannerSeesWhatItShould:
    def test_a_list_literal_argv_is_read_past_global_options(self) -> None:
        source = 'subprocess.run(["git", "-C", str(d), "-c", "a=b", "status", "--porcelain"])'

        assert list(bare_git_spawns(source)) == [(1, "status")]

    def test_a_spawn_call_with_git_as_its_first_argument_is_read(self) -> None:
        source = 'await asyncio.create_subprocess_exec("git", "diff", cwd=d)'

        assert list(bare_git_spawns(source)) == [(1, "diff")]

    def test_a_subcommand_that_is_not_a_literal_is_dynamic(self) -> None:
        assert list(bare_git_spawns('subprocess.run(["git", "-C", d, *args])')) == [(1, _DYNAMIC)]

    def test_the_hardened_argv_and_a_which_lookup_are_not_spawns(self) -> None:
        source = 'argv = hardened_git_argv(("status",), repo_dir=d)\nshutil.which("git")\ntokens.index("git")'

        assert list(bare_git_spawns(source)) == []
