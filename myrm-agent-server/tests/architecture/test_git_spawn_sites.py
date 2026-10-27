"""A git command that reads the index or the working tree goes through the hardened argv, or is listed here with why.

[INPUT]
- app/**/*.py: every ``git`` argv written as a list literal or as the first argument of a spawn call

[OUTPUT]
- Fails when a command that reads or writes the working tree is spawned with a bare ``git`` argv and is not listed
  below with its reason, or when a listed site no longer exists (so the list cannot rot).

[POS]
tests/architecture/test_git_spawn_sites.py — server half of the guard for ``myrm_agent_harness.core.security.safe_git``:
a repository's own config can pick programs that git runs during ``status`` / ``diff``, so a new inspection call
written the plain way would reopen that route.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

_APP = Path(__file__).resolve().parents[2] / "app"

# Subcommands that read the index or working tree, or check a tree out: where git consults repository-chosen programs.
_TREE_TOUCHING = frozenset(
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
    }
)
_DYNAMIC = "*"
_SPAWN_CALLS = frozenset({"run", "Popen", "check_output", "check_call", "create_subprocess_exec"})

# path under app/ -> (subcommands spawned bare there, why that is correct)
_BARE_GIT_SITES: dict[str, tuple[frozenset[str], str]] = {
    "core/utils/git_worktree.py": (
        frozenset({"worktree", "status", "add", "commit", "merge", "diff"}),
        "the worktree create / commit / merge flow: the repository's own hooks and filters take part in a commit, "
        "which a hardened argv would switch off; its status and conflict listing sit inside that flow",
    ),
    "services/git/worktree_service.py": (
        frozenset({"worktree"}),
        "`worktree list` reads no tree; `worktree add` checks one out, with the repository's own post-checkout hook "
        "and smudge filters",
    ),
    "services/kanban/task_runner/worktree/merge.py": (
        frozenset({"checkout"}),
        "the merge flow checks out the target branch with the repository's own hooks and filters",
    ),
    "services/kanban/race_lane_diff.py": (
        frozenset({_DYNAMIC}),
        "only `diff --numstat A...B` and `show <ref>:<path>`: object-to-object reads that touch neither the index nor "
        "the working tree and run no configured program",
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
    for path in sorted(_APP.rglob("*.py")):
        for _line, subcommand in bare_git_spawns(path.read_text(encoding="utf-8")):
            found.setdefault(path.relative_to(_APP).as_posix(), set()).add(subcommand)
    return found


def test_every_tree_touching_bare_git_spawn_is_listed_with_its_reason() -> None:
    unlisted = [
        f"{path}: git {subcommand}"
        for path, subcommands in _found().items()
        for subcommand in sorted(subcommands)
        if (subcommand in _TREE_TOUCHING or subcommand == _DYNAMIC)
        and subcommand not in _BARE_GIT_SITES.get(path, (frozenset(), ""))[0]
    ]

    assert not unlisted, (
        "build these with myrm_agent_harness.core.security.safe_git.hardened_git_argv(_async), "
        "or list them in _BARE_GIT_SITES with why:\n" + "\n".join(unlisted)
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

    def test_an_identity_prefix_does_not_hide_the_subcommand(self) -> None:
        source = 'await asyncio.to_thread(subprocess.run, ["git", *identity, "commit", "-m", message])'

        assert list(bare_git_spawns(source)) == [(1, "commit")]

    def test_a_subcommand_that_is_not_a_literal_is_dynamic(self) -> None:
        assert list(bare_git_spawns('subprocess.run(["git", *args])')) == [(1, _DYNAMIC)]

    def test_the_hardened_argv_and_a_which_lookup_are_not_spawns(self) -> None:
        source = 'argv = await hardened_git_argv_async(("status",), repo_dir=d)\nshutil.which("git")'

        assert list(bare_git_spawns(source)) == []
