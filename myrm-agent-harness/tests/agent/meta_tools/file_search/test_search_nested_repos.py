"""End-to-end tests: repositories nested inside a git checkout are searched, once per search tier.

git lists an untracked clone, or a submodule, as one entry instead of its files.

Covers:
- An untracked clone is searched with the ignore rules of its own repository, its subdirectories' ignore files included
- A directory the parent repository ignores hides a clone inside it
- A submodule, and a recorded gitlink, are searched without their ``.git`` marker; a gitlink with no checkout lists nothing
- A nested repository that git refuses to read is still searched, under the ignore files at its root
- The result cap holds across nested repositories
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.agent.meta_tools.file_search.search_probe import SearchRunner, hit_files, listed, write_tree

PARENT_FILES = {".gitignore": "*.log\n", "app.py": "needle\n", "debug.log": "needle\n"}
# ``build/`` is not ignored by the nested repository, so it is searched there like in any checkout.
NESTED_FILES = {".gitignore": "*.tmp\n", "main.py": "needle\n", "skip.tmp": "needle\n", "build/out.js": "needle\n"}
NESTED_VISIBLE = {".gitignore", "main.py", "build/out.js"}


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "protocol.file.allow=always",
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repository(root: Path, files: dict[str, str], *, committed: bool = False) -> Path:
    write_tree(root, files)
    _git(root, "init", "-q")
    if committed:
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "initial")
    return root


@pytest.fixture
def parent(tmp_path: Path, require_git: None) -> Path:
    return _repository(tmp_path / "parent", PARENT_FILES)


class TestUntrackedClone:
    async def test_is_searched_with_the_ignore_rules_of_its_own_repository(
        self, parent: Path, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        _repository(parent / "vendor" / "clone", NESTED_FILES)
        visible = {"app.py", ".gitignore"} | {f"vendor/clone/{name}" for name in NESTED_VISIBLE}

        assert listed(await run_glob(parent, "**/*")) == visible

        output = await run_grep(parent, "needle")
        searched = {"app.py", "vendor/clone/main.py", "vendor/clone/build/out.js"}
        assert hit_files(output, searched | {"debug.log", "vendor/clone/skip.tmp"}) == searched

    async def test_honours_the_ignore_files_of_its_subdirectories(
        self, parent: Path, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        files = {
            ".gitignore": "*.tmp\n",
            "main.py": "needle\n",
            "pkg/.gitignore": "generated/\n",
            "pkg/mod.py": "needle\n",
            "pkg/generated/out.py": "needle\n",
        }
        _repository(parent / "vendor" / "clone", files)
        visible = {".gitignore", "main.py", "pkg/.gitignore", "pkg/mod.py"}

        assert listed(await run_glob(parent, "**/*")) == {"app.py", ".gitignore"} | {
            f"vendor/clone/{name}" for name in visible
        }

        output = await run_grep(parent, "needle")
        searched = {"app.py", "vendor/clone/main.py", "vendor/clone/pkg/mod.py"}
        assert hit_files(output, searched | {"vendor/clone/pkg/generated/out.py"}) == searched

    async def test_is_hidden_by_a_directory_the_parent_ignores(self, parent: Path, run_glob: SearchRunner) -> None:
        (parent / ".gitignore").write_text("*.log\nvendor/\n", encoding="utf-8")
        _repository(parent / "vendor" / "clone", NESTED_FILES)

        assert listed(await run_glob(parent, "**/*")) == {"app.py", ".gitignore"}


class TestSubmodules:
    async def test_a_submodule_is_searched_without_its_git_file(
        self, parent: Path, tmp_path: Path, run_glob: SearchRunner
    ) -> None:
        source = _repository(tmp_path / "source", NESTED_FILES, committed=True)
        _git(parent, "submodule", "add", "-q", str(source), "libs/dep")

        files = listed(await run_glob(parent, "libs/**/*"))

        assert files == {f"libs/dep/{name}" for name in NESTED_VISIBLE}

    async def test_a_recorded_gitlink_is_searched(self, parent: Path, run_glob: SearchRunner) -> None:
        dep = _repository(parent / "libs" / "dep", NESTED_FILES, committed=True)
        _git(parent, "update-index", "--add", "--cacheinfo", f"160000,{_git(dep, 'rev-parse', 'HEAD')},libs/dep")

        files = listed(await run_glob(parent, "libs/**/*"))

        assert files == {f"libs/dep/{name}" for name in NESTED_VISIBLE}

    async def test_a_gitlink_without_a_checkout_lists_nothing(
        self, parent: Path, tmp_path: Path, run_glob: SearchRunner
    ) -> None:
        source = _repository(tmp_path / "source", NESTED_FILES, committed=True)
        _git(parent, "update-index", "--add", "--cacheinfo", f"160000,{_git(source, 'rev-parse', 'HEAD')},libs/dep")
        (parent / "libs" / "dep").mkdir(parents=True)

        assert listed(await run_glob(parent, "libs/**/*")) == set()


@pytest.mark.parametrize("engine", ["python"], indirect=True)
class TestNestedRepositoryGitRefusesToRead:
    async def test_is_walked_under_the_ignore_files_at_its_root(self, parent: Path, run_glob: SearchRunner) -> None:
        clone = _repository(parent / "vendor" / "clone", NESTED_FILES)
        # A conditional include is the one repository setting hardened git refuses to run under.
        with (clone / ".git" / "config").open("a", encoding="utf-8") as config:
            config.write('[includeIf "gitdir:/"]\n\tpath = elsewhere\n')

        files = listed(await run_glob(parent, "**/*"))

        assert files == {"app.py", ".gitignore"} | {f"vendor/clone/{name}" for name in NESTED_VISIBLE}


class TestResultCap:
    async def test_holds_across_nested_repositories(self, parent: Path, run_glob: SearchRunner) -> None:
        for index in range(3):
            _repository(parent / "vendor" / f"clone{index}", {f"f{number}.py": "x\n" for number in range(4)})

        assert len(listed(await run_glob(parent, "**/*.py", max_results=5))) == 5
