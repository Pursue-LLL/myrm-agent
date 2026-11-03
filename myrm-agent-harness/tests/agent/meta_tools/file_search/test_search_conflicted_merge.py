"""End-to-end tests: a repository stopped on a merge conflict lists each file once, once per search tier.

git's index holds three stages of an unmerged path, so ``git ls-files --cached`` names that path three times.

Covers:
- ``collect_candidate_files`` names an unmerged path once
- glob_tool lists the file once and grep_tool finds its conflict markers once
- The Python tier counts the file once among the files it searched
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search.fallback_discovery import collect_candidate_files
from tests.agent.meta_tools.file_search.search_probe import SearchRunner, git, listed, write_tree


@pytest.fixture
def conflicted(tmp_path: Path, require_git: None) -> Path:
    """A repository whose merge stopped on a conflict in ``a.txt``; ``b.txt`` merged cleanly."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    write_tree(root, {"a.txt": "base\n", "b.txt": "other\n"})
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "switch", "-qc", "feature")
    write_tree(root, {"a.txt": "feature\n"})
    git(root, "commit", "-qam", "feature")
    git(root, "switch", "-q", "main")
    write_tree(root, {"a.txt": "main\n"})
    git(root, "commit", "-qam", "main")
    git(root, "merge", "feature", check=False)
    assert git(root, "ls-files", "--unmerged"), "the merge must stop on a conflict"
    return root


class TestDiscovery:
    def test_an_unmerged_path_is_named_once(self, conflicted: Path) -> None:
        files = collect_candidate_files(
            search_root=conflicted, file_pattern="**/*", max_files=100, include_ignored=False
        )

        assert sorted(path.name for path in files) == ["a.txt", "b.txt"]


class TestTools:
    async def test_glob_lists_the_unmerged_file_once(self, conflicted: Path, run_glob: SearchRunner) -> None:
        output = await run_glob(conflicted, "*.txt")

        assert output.splitlines()[0] == "Found 2 file(s) matching '*.txt':"
        assert listed(output) == {"a.txt", "b.txt"}

    async def test_grep_finds_a_conflict_marker_once(self, conflicted: Path, run_grep: SearchRunner) -> None:
        output = await run_grep(conflicted, "^<<<<<<<")

        assert output.startswith("Found 1 match(es) for '^<<<<<<<'")


@pytest.mark.parametrize("engine", ["python"], indirect=True)
class TestPythonTierCount:
    async def test_the_unmerged_file_is_counted_once(self, conflicted: Path, run_grep: SearchRunner) -> None:
        output = await run_grep(conflicted, "^<<<<<<<")

        assert output.splitlines()[0] == "Found 1 match(es) for '^<<<<<<<' (searched 2 file(s)):"
