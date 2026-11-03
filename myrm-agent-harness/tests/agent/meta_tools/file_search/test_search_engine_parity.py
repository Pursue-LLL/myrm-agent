"""End-to-end tests for glob_tool and grep_tool on real directory trees, once per search tier.

Covers:
- Anchored patterns, ``**`` and brace alternatives behave identically on the ripgrep and Python tiers
- Match-all patterns never leak ignored or version-control content, and hidden files are searched like any other
- Ignore files apply in directories that are not git repositories
- ``include_ignored`` lists ignored files but never version-control internals
- Hitting the result cap stops the search and returns exactly the capped result set
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from myrm_agent_harness.utils.errors import ToolError
from tests.agent.meta_tools.file_search.search_probe import SearchRunner, hit_files, listed, write_tree

PROJECT_FILES = {
    ".gitignore": "node_modules/\nbuild/\n*.log\n",
    ".env": "SECRET=needle\n",
    "src/app.ts": "const needle = 1\n",
    "src/index.py": "needle = 1\n",
    "src/pkg/mod.py": "def mod():\n    return 'needle'\n",
    "src/util/helper.ts": "export const h = 'needle'\n",
    "tests/test_index.py": "needle = 2\n",
    "config/app.yaml": "key: needle\n",
    "config/app.yml": "key: needle\n",
    "config/settings.json": '{"k": "needle"}\n',
    "docs/readme.md": "needle\n",
    "settings/config": "[core]\nneedle\n",
    "node_modules/lib/index.js": "needle\n",
    "build/out.js": "needle\n",
    "debug.log": "needle\n",
}
VISIBLE_FILES = {
    ".gitignore",
    ".env",
    "src/app.ts",
    "src/index.py",
    "src/pkg/mod.py",
    "src/util/helper.ts",
    "tests/test_index.py",
    "config/app.yaml",
    "config/app.yml",
    "config/settings.json",
    "docs/readme.md",
    "settings/config",
}
IGNORED_FILES = {"node_modules/lib/index.js", "build/out.js", "debug.log"}


@pytest.fixture(params=["plain", "git"])
def project(request: pytest.FixtureRequest) -> Path:
    """The same project tree, once as a plain directory and once as a git repository."""
    if request.param == "git":
        request.getfixturevalue("require_git")
        base: Path = request.getfixturevalue("tmp_path")
    else:
        base = request.getfixturevalue("plain_dir")
    root = base / "project"
    root.mkdir()
    write_tree(root, PROJECT_FILES)
    if request.param == "git":
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


@pytest.fixture
def git_project(tmp_path: Path, require_git: None) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    write_tree(root, PROJECT_FILES)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


ALL_FILES = set(PROJECT_FILES)


class TestGlobPatterns:
    async def test_anchored_pattern_does_not_descend(self, project: Path, run_glob: SearchRunner) -> None:
        output = await run_glob(project, "src/*.ts")
        assert listed(output) == {"src/app.ts"}

    async def test_double_star_between_segments(self, project: Path, run_glob: SearchRunner) -> None:
        output = await run_glob(project, "src/**/*.py")
        assert listed(output) == {"src/index.py", "src/pkg/mod.py"}

    async def test_brace_alternatives(self, project: Path, run_glob: SearchRunner) -> None:
        output = await run_glob(project, "**/*.{yaml,yml}")
        assert listed(output) == {"config/app.yaml", "config/app.yml"}

    async def test_pattern_without_slash_matches_at_any_depth(self, project: Path, run_glob: SearchRunner) -> None:
        output = await run_glob(project, "*.py")
        assert listed(output) == {"src/index.py", "src/pkg/mod.py", "tests/test_index.py"}

    async def test_leading_slash_anchors_at_root(self, project: Path, run_glob: SearchRunner) -> None:
        output = await run_glob(project, "/.env")
        assert listed(output) == {".env"}

    @pytest.mark.parametrize("pattern", ["*", "**", "**/*"])
    async def test_match_all_lists_only_visible_files(
        self, project: Path, run_glob: SearchRunner, pattern: str
    ) -> None:
        output = await run_glob(project, pattern)
        assert listed(output) == VISIBLE_FILES

    async def test_ignore_files_apply_to_specific_patterns(self, project: Path, run_glob: SearchRunner) -> None:
        output = await run_glob(project, "**/*.js")
        assert "No files found" in output

    async def test_include_ignored_lists_ignored_files(self, project: Path, run_glob: SearchRunner) -> None:
        output = await run_glob(project, "*", include_ignored=True)
        files = listed(output)
        assert files >= IGNORED_FILES
        assert files >= VISIBLE_FILES

    async def test_include_ignored_never_lists_version_control_internals(
        self, git_project: Path, run_glob: SearchRunner
    ) -> None:
        output = await run_glob(git_project, "**/*", include_ignored=True)
        assert not any(entry.startswith(".git/") for entry in listed(output))

    @pytest.mark.parametrize("pattern", ["", "a\x00b"])
    async def test_invalid_pattern_is_rejected(self, project: Path, run_glob: SearchRunner, pattern: str) -> None:
        with pytest.raises(ToolError, match="Invalid pattern"):
            await run_glob(project, pattern)


class TestGrepFilePatterns:
    async def test_anchored_file_pattern(self, project: Path, run_grep: SearchRunner) -> None:
        output = await run_grep(project, "needle", file_pattern="src/*.ts")
        assert hit_files(output, ALL_FILES) == {"src/app.ts"}

    async def test_leading_dot_slash_file_pattern(self, project: Path, run_grep: SearchRunner) -> None:
        output = await run_grep(project, "needle", file_pattern="./src/*.ts")
        assert hit_files(output, ALL_FILES) == {"src/app.ts"}

    async def test_double_star_file_pattern(self, project: Path, run_grep: SearchRunner) -> None:
        output = await run_grep(project, "needle", file_pattern="src/**/*.ts")
        assert hit_files(output, ALL_FILES) == {"src/app.ts", "src/util/helper.ts"}

    async def test_brace_file_pattern(self, project: Path, run_grep: SearchRunner) -> None:
        output = await run_grep(project, "needle", file_pattern="**/*.{yaml,yml}")
        assert hit_files(output, ALL_FILES) == {"config/app.yaml", "config/app.yml"}

    @pytest.mark.parametrize("file_pattern", ["**/*", "*", "**"])
    async def test_match_all_searches_hidden_files_but_not_ignored_ones(
        self, project: Path, run_grep: SearchRunner, file_pattern: str
    ) -> None:
        output = await run_grep(project, "needle", file_pattern=file_pattern)
        hits = hit_files(output, ALL_FILES)
        assert hits.isdisjoint(IGNORED_FILES)
        assert ".env" in hits
        assert {"src/app.ts", "src/pkg/mod.py", "config/settings.json"} <= hits

    async def test_ignore_files_apply_by_default(self, project: Path, run_grep: SearchRunner) -> None:
        output = await run_grep(project, "needle")
        assert hit_files(output, IGNORED_FILES) == set()

    async def test_version_control_internals_are_never_searched(
        self, git_project: Path, run_grep: SearchRunner
    ) -> None:
        output = await run_grep(git_project, r"\[core\]", file_pattern="**/config")
        assert "settings/config" in output
        assert ".git/config" not in output

    async def test_invalid_file_pattern_is_rejected(self, project: Path, run_grep: SearchRunner) -> None:
        with pytest.raises(ToolError, match="Invalid file pattern"):
            await run_grep(project, "needle", file_pattern="a\x00b")


@pytest.fixture
def bulk_project(tmp_path: Path) -> Path:
    """Far more matching files than the result cap, so ripgrep is stopped early."""
    root = tmp_path / "bulk"
    for directory in range(20):
        folder = root / f"package_{directory:02d}" / "implementation_modules"
        folder.mkdir(parents=True)
        for index in range(60):
            (folder / f"generated_source_file_{index:03d}.py").write_text(
                f"needle_{directory}_{index} = {'x' * 80}\n", encoding="utf-8"
            )
    return root


class TestResultCap:
    """The early stop itself is exercised against a real subprocess in test_rg_runner."""

    async def test_glob_returns_promptly_at_cap(self, bulk_project: Path, run_glob: SearchRunner) -> None:
        output = await run_glob(bulk_project, "**/*.py", max_results=100)
        assert len(listed(output)) == 100

    async def test_grep_returns_promptly_at_cap(self, bulk_project: Path, run_grep: SearchRunner) -> None:
        output = await run_grep(bulk_project, "needle_", max_results=100)
        assert "Found 100 match(es)" in output
