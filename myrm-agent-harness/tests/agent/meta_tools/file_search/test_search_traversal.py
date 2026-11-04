"""End-to-end tests for what glob_tool and grep_tool traverse, once per search tier.

Covers:
- Ignore files above a non-git workspace never hide it; those of an enclosing repository still apply
- Dependency and build directories are skipped in plain folders, and only there
- Hidden files and directories are searched
- Symbolic links are never followed out of the workspace
- A file name that holds a line break is one entry on both tiers
- ripgrep ignores the user's own configuration
- ripgrep failures: partial output survives; unparseable patterns, timeouts and a glob listing that fails without
  naming a file fall back to the Python tier
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search import glob_tool, grep_tool
from myrm_agent_harness.agent.meta_tools.file_search._rg_runner import RgRunResult
from myrm_agent_harness.agent.meta_tools.file_search.rg_traversal import has_git_ancestor, rg_traversal_args
from tests.agent.meta_tools.file_search.search_probe import SearchRunner, hit_files, listed, write_tree

DEPENDENCY_AND_BUILD_TREE = {
    "src/app.js": "needle\n",
    "docs/build": "needle\n",
    "node_modules/pkg/index.js": "needle\n",
    "packages/ui/node_modules/x/index.js": "needle\n",
    "dist/out.js": "needle\n",
    "build/out.js": "needle\n",
    ".venv/lib/mod.py": "needle\n",
    "venv/lib/mod.py": "needle\n",
    "__pycache__/m.py": "needle\n",
    ".cache/blob.txt": "needle\n",
}
# A file that merely shares its name with a build directory is ordinary content.
DEPENDENCY_AND_BUILD_VISIBLE = {"src/app.js", "docs/build"}


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


@pytest.fixture(params=["plain", "git"])
def workspace(request: pytest.FixtureRequest) -> Path:
    """An empty workspace directory, once plain and once as a git checkout."""
    if request.param == "git":
        request.getfixturevalue("require_git")
        base: Path = request.getfixturevalue("tmp_path")
    else:
        base = request.getfixturevalue("plain_dir")
    root = base / "work"
    root.mkdir()
    if request.param == "git":
        _git_init(root)
    return root


class TestGitAncestor:
    def test_directory_marker(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert has_git_ancestor(nested)

    def test_file_marker_of_a_worktree(self, tmp_path: Path) -> None:
        (tmp_path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/w\n", encoding="utf-8")
        assert has_git_ancestor(tmp_path)

    def test_no_marker(self, plain_dir: Path) -> None:
        assert not has_git_ancestor(plain_dir)


class TestTraversalArguments:
    def test_user_configuration_is_always_ignored(self, plain_dir: Path) -> None:
        assert rg_traversal_args(plain_dir)[0] == "--no-config"
        assert rg_traversal_args(plain_dir, include_ignored=True)[0] == "--no-config"

    def test_plain_folder_skips_parent_and_global_ignore_files_and_dependency_directories(
        self, plain_dir: Path
    ) -> None:
        arguments = rg_traversal_args(plain_dir)
        assert "--no-ignore-parent" in arguments
        assert "--no-ignore-global" in arguments
        assert any("node_modules" in argument for argument in arguments)

    def test_git_checkout_leaves_ignore_decisions_to_git(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        arguments = rg_traversal_args(tmp_path)
        assert "--no-ignore-parent" not in arguments
        assert "--no-ignore-global" not in arguments
        assert not any("node_modules" in argument for argument in arguments)

    def test_include_ignored_turns_ignore_files_and_pruning_off(self, plain_dir: Path) -> None:
        arguments = rg_traversal_args(plain_dir, include_ignored=True)
        assert "--no-ignore" in arguments
        assert not any("node_modules" in argument for argument in arguments)


class TestIgnoreFilesAboveTheWorkspace:
    async def test_stray_ignore_file_does_not_hide_a_non_git_workspace(
        self, plain_dir: Path, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        (plain_dir / ".gitignore").write_text("*\n!*/\n", encoding="utf-8")
        workspace = plain_dir / "work"
        write_tree(workspace, {"src/a.py": "needle\n"})

        assert listed(await run_glob(workspace, "**/*.py")) == {"src/a.py"}
        assert hit_files(await run_grep(workspace, "needle"), {"src/a.py"}) == {"src/a.py"}

    async def test_global_ignore_file_of_the_user_does_not_hide_a_non_git_workspace(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        home = plain_dir / "home"
        write_tree(home, {".config/git/ignore": "*.notes\n"})
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
        workspace = plain_dir / "work"
        files = {"a.py": "needle\n", "todo.notes": "needle\n"}
        write_tree(workspace, files)

        assert listed(await run_glob(workspace, "**/*")) == set(files)
        assert hit_files(await run_grep(workspace, "needle"), set(files)) == set(files)

    async def test_ignore_file_of_the_enclosing_repository_still_applies(
        self, tmp_path: Path, require_git: None, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        repo = tmp_path / "repo"
        write_tree(repo, {".gitignore": "*.log\n", "pkg/a.py": "needle\n", "pkg/a.log": "needle\n"})
        _git_init(repo)

        assert listed(await run_glob(repo / "pkg", "*")) == {"a.py"}
        assert hit_files(await run_grep(repo / "pkg", "needle"), {"a.py", "a.log"}) == {"a.py"}


class TestDependencyAndBuildDirectories:
    async def test_skipped_in_a_plain_folder(
        self, plain_dir: Path, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, DEPENDENCY_AND_BUILD_TREE)

        assert listed(await run_glob(plain_dir, "**/*")) == DEPENDENCY_AND_BUILD_VISIBLE
        output = await run_grep(plain_dir, "needle")
        assert hit_files(output, set(DEPENDENCY_AND_BUILD_TREE)) == DEPENDENCY_AND_BUILD_VISIBLE

    async def test_listed_when_ignored_files_are_requested(self, plain_dir: Path, run_glob: SearchRunner) -> None:
        write_tree(plain_dir, DEPENDENCY_AND_BUILD_TREE)

        assert listed(await run_glob(plain_dir, "**/*", include_ignored=True)) == set(DEPENDENCY_AND_BUILD_TREE)

    async def test_left_to_git_inside_a_checkout(
        self, tmp_path: Path, require_git: None, run_glob: SearchRunner
    ) -> None:
        write_tree(tmp_path, DEPENDENCY_AND_BUILD_TREE)
        _git_init(tmp_path)

        assert listed(await run_glob(tmp_path, "**/*")) == set(DEPENDENCY_AND_BUILD_TREE)


class TestHiddenFiles:
    async def test_hidden_directories_are_listed_and_searched(
        self, workspace: Path, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        files = {".github/workflows/ci.yml": "needle\n", "src/a.py": "needle\n"}
        write_tree(workspace, files)

        assert listed(await run_glob(workspace, "**/*.yml")) == {".github/workflows/ci.yml"}
        assert hit_files(await run_grep(workspace, "needle"), set(files)) == set(files)


@pytest.mark.skipif(sys.platform == "win32", reason="creating symbolic links needs elevated rights on Windows")
class TestSymbolicLinks:
    async def test_links_are_not_followed_out_of_the_workspace(
        self, workspace: Path, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        outside = workspace.parent / "outside"
        write_tree(outside, {"secret.py": "needle\n"})
        write_tree(workspace, {"own.py": "needle\n"})
        (workspace / "linked.py").symlink_to(outside / "secret.py")
        (workspace / "linked_dir").symlink_to(outside, target_is_directory=True)

        assert listed(await run_glob(workspace, "**/*.py")) == {"own.py"}
        assert hit_files(await run_grep(workspace, "needle"), {"own.py", "linked.py", "secret.py"}) == {"own.py"}


@pytest.mark.skipif(sys.platform == "win32", reason="a Windows file name cannot hold a line break")
class TestUnusualFileNames:
    async def test_a_name_holding_a_line_break_is_one_entry(self, workspace: Path, run_glob: SearchRunner) -> None:
        # Cut at its line break, the last name would list /etc/hosts from outside the search root.
        names = ["plain.txt", "two\nlines.txt", "ends-with-return\r", "dir\n/etc/hosts"]
        write_tree(workspace, {name: "x\n" for name in names})

        output = await run_glob(workspace, "**/*")

        assert f"Found {len(names)} file(s)" in output
        assert all(f" {name}\n" in output for name in names)
        assert "\n /etc/hosts\n" not in output


@pytest.mark.parametrize("engine", ["ripgrep"], indirect=True)
class TestRipgrepConfiguration:
    async def test_user_configuration_does_not_change_results(
        self,
        plain_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
        run_glob: SearchRunner,
        run_grep: SearchRunner,
    ) -> None:
        write_tree(plain_dir, {".gitignore": "ignored.txt\n", "ignored.txt": "needle\n", "kept.txt": "needle\n"})
        config = plain_dir / "rg.conf"
        config.write_text("--no-ignore\n", encoding="utf-8")
        monkeypatch.setenv("RIPGREP_CONFIG_PATH", str(config))

        assert listed(await run_glob(plain_dir, "*.txt")) == {"kept.txt"}
        assert hit_files(await run_grep(plain_dir, "needle"), {"kept.txt", "ignored.txt"}) == {"kept.txt"}


@pytest.mark.parametrize("engine", ["ripgrep"], indirect=True)
class TestRipgrepFailures:
    @pytest.mark.skipif(sys.platform == "win32", reason="directory permissions are not enforced the same way")
    async def test_unreadable_directory_keeps_the_matches_already_found(
        self, plain_dir: Path, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("root reads every directory")
        write_tree(plain_dir, {f"ok/f{index:02d}.txt": "needle\n" for index in range(30)})
        write_tree(plain_dir, {"locked/h.txt": "needle\n"})
        locked = plain_dir / "locked"
        locked.chmod(0)
        try:
            # More matching files than the Python tier would scan, so a fallback would visibly lose matches.
            grep_output = await run_grep(plain_dir, "needle", max_files=10)
            glob_output = await run_glob(plain_dir, "**/*.txt")
        finally:
            locked.chmod(0o755)

        assert "Found 30 match(es)" in grep_output
        assert len(listed(glob_output)) == 30

    async def test_pattern_ripgrep_cannot_parse_is_searched_by_the_python_tier(
        self, plain_dir: Path, run_grep: SearchRunner
    ) -> None:
        write_tree(plain_dir, {"a.py": "needle = 1\n", "b.py": "needle = 2\n"})

        output = await run_grep(plain_dir, r"needle(?= = 1)")

        assert hit_files(output, {"a.py", "b.py"}) == {"a.py"}

    async def test_grep_falls_back_when_ripgrep_times_out(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, run_grep: SearchRunner
    ) -> None:
        async def time_out(*_args: object, **_kwargs: object) -> None:
            raise TimeoutError

        monkeypatch.setattr(grep_tool, "run_rg", time_out)
        write_tree(plain_dir, {"a.py": "needle\n"})

        assert hit_files(await run_grep(plain_dir, "needle"), {"a.py"}) == {"a.py"}

    async def test_glob_falls_back_when_ripgrep_cannot_run(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, run_glob: SearchRunner
    ) -> None:
        async def cannot_run(*_args: object, **_kwargs: object) -> None:
            raise OSError("exec failed")

        monkeypatch.setattr(glob_tool, "run_rg", cannot_run)
        write_tree(plain_dir, {"a.py": "needle\n"})

        assert listed(await run_glob(plain_dir, "**/*.py")) == {"a.py"}

    async def test_glob_falls_back_when_ripgrep_fails_without_listing_a_file(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, run_glob: SearchRunner
    ) -> None:
        async def fails(*_args: object, **_kwargs: object) -> RgRunResult:
            return RgRunResult(returncode=2, stderr="permission denied", stopped_early=False)

        monkeypatch.setattr(glob_tool, "run_rg", fails)
        write_tree(plain_dir, {"a.py": "needle\n"})

        assert listed(await run_glob(plain_dir, "**/*.py")) == {"a.py"}

    async def test_glob_keeps_the_files_ripgrep_listed_before_it_failed(
        self, plain_dir: Path, monkeypatch: pytest.MonkeyPatch, run_glob: SearchRunner
    ) -> None:
        async def lists_one_then_fails(
            _cmd: Sequence[str], *, on_line: Callable[[bytes], bool], **_kwargs: object
        ) -> RgRunResult:
            on_line(b"listed.py\0")
            return RgRunResult(returncode=2, stderr="permission denied", stopped_early=False)

        monkeypatch.setattr(glob_tool, "run_rg", lists_one_then_fails)
        write_tree(plain_dir, {"listed.py": "", "unlisted.py": ""})

        assert listed(await run_glob(plain_dir, "**/*.py")) == {"listed.py"}
