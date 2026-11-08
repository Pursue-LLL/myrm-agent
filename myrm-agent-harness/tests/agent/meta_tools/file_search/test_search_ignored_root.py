"""End-to-end tests: a search root that git itself ignores is still searched, once per search tier.

Asking for ``node_modules/lodash`` or a virtualenv by name is a deliberate request. git lists nothing below a
directory it ignores, so the listing alone cannot tell such a root from an empty one.

Covers:
- glob and grep below directories a repository ignores (dependencies, virtualenv, logs, build output)
- A directory whose contents alone are ignored (``partial/*``) and an empty directory stay empty
- The rest of the repository is searched as before
- Neither tier reads a ``.gitignore`` above an ignored root that ignores everything below itself (a virtualenv's own)
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
# Ways a tool writes a ``.gitignore`` that ignores everything below its directory; git reads each as such.
CATCH_ALL_FILES = {
    "star": b"*\n",
    "venv": b"# Created by venv; see https://docs.python.org/3/library/venv.html\n*\n",
    "carriage_return": b"*\r\n",
    "trailing_spaces": b"*  \n",
    "anchored": b"/*\n",
    "double_star": b"**\n",
    "anchored_double_star": b"/**\n",
    "recursive": b"**/*\n",
    "among_other_rules": b"*.pyc\n\n*\nbuild/\n",
    "byte_order_mark": b"\xef\xbb\xbf*\n",
}


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


class TestIgnoreFileAboveTheRoot:
    # A virtual environment, uv or a tool cache writes its own ``.gitignore`` into the directory it owns. The
    # repository ignores that directory, so neither tier may let the file hide what lies below a search root inside it.
    @pytest.mark.parametrize("content", CATCH_ALL_FILES.values(), ids=CATCH_ALL_FILES)
    async def test_glob_walks_the_root_like_a_plain_folder(
        self, repo: Path, run_glob: SearchRunner, content: bytes
    ) -> None:
        (repo / ".venv" / ".gitignore").write_bytes(content)

        assert listed(await run_glob(repo, "**/*", path=".venv/lib")) == {"mod.py"}

    async def test_grep_walks_the_root_like_a_plain_folder(self, repo: Path, run_grep: SearchRunner) -> None:
        (repo / ".venv" / ".gitignore").write_bytes(b"*\n")

        output = await run_grep(repo, "needle", path=".venv/lib")

        assert "Found 1 match(es)" in output
        assert "mod.py" in output
