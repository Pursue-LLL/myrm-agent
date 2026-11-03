"""End-to-end tests: a search root that git itself ignores is still searched, once per search tier.

Asking for ``node_modules/lodash`` or a virtualenv by name is a deliberate request. git lists nothing below a
directory it ignores, so the listing alone cannot tell such a root from an empty one.

Covers:
- glob and grep below directories a repository ignores (dependencies, virtualenv, logs, build output)
- A directory whose contents alone are ignored (``partial/*``) and an empty directory stay empty
- The rest of the repository is searched as before
- The Python tier does not read an ignore file above an ignored root (a virtualenv's own ``.gitignore`` of ``*``)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.agent.meta_tools.file_search.search_probe import SearchRunner, listed, write_tree

REPO_FILES = {
    ".gitignore": "node_modules/\n.venv/\nlogs\ndist\npartial/*\n",
    "src/app.py": "needle = 1\n",
    "node_modules/lodash/index.js": "needle\n",
    ".venv/lib/mod.py": "needle\n",
    "logs/app.txt": "needle\n",
    "dist/out.js": "needle\n",
    "partial/a.txt": "needle\n",
}
# Ignored search root and a file below it, relative to that root.
IGNORED_ROOTS = [
    ("node_modules/lodash", "index.js"),
    (".venv", "lib/mod.py"),
    ("logs", "app.txt"),
    ("dist", "out.js"),
]


@pytest.fixture
def repo(tmp_path: Path, require_git: None) -> Path:
    root = tmp_path / "repo"
    write_tree(root, REPO_FILES)
    (root / "empty").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


class TestIgnoredRoot:
    @pytest.mark.parametrize(("root", "witness"), IGNORED_ROOTS)
    async def test_glob_lists_the_files_below_it(
        self, repo: Path, run_glob: SearchRunner, root: str, witness: str
    ) -> None:
        assert witness in listed(await run_glob(repo, "**/*", path=root))

    @pytest.mark.parametrize(("root", "witness"), IGNORED_ROOTS)
    async def test_grep_searches_the_files_below_it(
        self, repo: Path, run_grep: SearchRunner, root: str, witness: str
    ) -> None:
        output = await run_grep(repo, "needle", path=root)

        assert "Found 1 match(es)" in output
        assert Path(witness).name in output

    async def test_the_repository_itself_is_unchanged(self, repo: Path, run_glob: SearchRunner) -> None:
        assert listed(await run_glob(repo, "**/*")) == {".gitignore", "src/app.py"}


class TestRootsThatAreNotIgnored:
    @pytest.mark.parametrize("root", ["partial", "empty"])
    async def test_glob_finds_nothing_in_a_directory_without_visible_files(
        self, repo: Path, run_glob: SearchRunner, root: str
    ) -> None:
        assert "No files found" in await run_glob(repo, "**/*", path=root)

    async def test_grep_finds_nothing_in_a_directory_without_visible_files(
        self, repo: Path, run_grep: SearchRunner
    ) -> None:
        assert "No matches found" in await run_grep(repo, "needle", path="partial")


@pytest.mark.parametrize("engine", ["python"], indirect=True)
class TestIgnoreFileAboveTheRoot:
    async def test_python_tier_walks_the_root_like_a_plain_folder(self, repo: Path, run_glob: SearchRunner) -> None:
        # A virtual environment writes its own ``.gitignore`` of ``*``; ripgrep honours it and finds nothing below.
        write_tree(repo, {".venv/.gitignore": "*\n"})

        assert listed(await run_glob(repo, "**/*", path=".venv/lib")) == {"mod.py"}
