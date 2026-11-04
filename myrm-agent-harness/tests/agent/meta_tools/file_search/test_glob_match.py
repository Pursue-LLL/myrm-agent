"""Tests for glob_match — glob semantics shared by the ripgrep and Python search tiers.

Covers:
- Wildcards, ``**``, character classes, hidden files
- Anchoring and ``./`` normalisation
- Brace expansion (nested, literal, limits)
- Validation errors
- Stacked wildcards stay fast to evaluate
- Parity with ripgrep's own ``--glob`` matching over a fixed tree
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search.glob_match import (
    compile_glob,
    glob_matches,
    is_match_all,
    normalize_glob,
)

TREE_FILES = (
    "a.py",
    "b.txt",
    "a.b.c.py",
    ".env",
    ".hidden/x.py",
    "src/a.py",
    "src/b.ts",
    "src/pkg/mod.py",
    "src/pkg/deep/z.py",
    "src/util/helper.ts",
    "tests/test_a.py",
    "tests/test_b.py",
    "docs/readme.md",
    "docs/GUIDE.MD",
    "config/app.yaml",
    "config/app.yml",
    "config/settings.json",
    "my dir/file name.py",
    "unicode/文件.py",
)

PARITY_PATTERNS = (
    "*.py",
    "**/*.py",
    "src/*.py",
    "src/*.ts",
    "src/**/*.py",
    "src/**",
    "src/**/z.py",
    "src/*/*.py",
    "src/p*/**/*.py",
    "**/pkg/*.py",
    "**/deep/**",
    "**/test_*.py",
    "test_*.py",
    "tests/test_?.py",
    "*.{py,ts}",
    "**/*.{yaml,yml,json}",
    "src/{pkg,util}/*",
    "**/{a,b}.py",
    "config/*",
    "docs/*.md",
    "docs/*.MD",
    "[ab].txt",
    "a.?y",
    "/a.py",
    "/src/*.ts",
    "/src/**/*.py",
    "./src/*.py",
    "  *.py \n",
    "helper.ts",
    "**/helper.ts",
    "src/pkg/mod.py",
    ".env",
    ".*",
    "**/.hidden/*",
    "my dir/*.py",
    "unicode/*.py",
    "*.nope",
    "nope/**",
    "*",
    "**",
    "**/*",
)


class TestMatching:
    @pytest.mark.parametrize(
        ("pattern", "path", "expected"),
        [
            ("*.py", "a.py", True),
            ("*.py", "src/pkg/a.py", True),
            ("*.py", "a.pyc", False),
            ("*.PY", "a.py", False),
            ("src/*.py", "src/a.py", True),
            ("src/*.py", "src/pkg/a.py", False),
            ("src/**/*.py", "src/a.py", True),
            ("src/**/*.py", "src/pkg/deep/a.py", True),
            ("src/**/*.py", "lib/src/a.py", False),
            ("**/*.py", "a.py", True),
            ("**/*.py", "a/b/c.py", True),
            ("**/test_*.py", "tests/test_a.py", True),
            ("**/test_*.py", "tests/a.py", False),
            ("a?.py", "ab.py", True),
            ("a?.py", "a/.py", False),
            ("[ab].txt", "a.txt", True),
            ("[ab].txt", "c.txt", False),
            ("*", ".env", True),
            ("*", "src/.env", True),
            ("**/*", ".git/config", True),
        ],
    )
    def test_match(self, pattern: str, path: str, expected: bool) -> None:
        assert glob_matches(path, pattern) is expected

    def test_leading_slash_anchors_at_root(self) -> None:
        assert glob_matches("a.py", "/a.py")
        assert not glob_matches("src/a.py", "/a.py")
        assert glob_matches("src/a.py", "/src/*.py")

    def test_leading_dot_slash_is_ignored(self) -> None:
        assert compile_glob("./src/*.py").pattern == compile_glob("src/*.py").pattern
        assert glob_matches("src/a.py", "./src/*.py")
        assert not glob_matches("lib/src/a.py", "./src/*.py")

    def test_surrounding_whitespace_is_ignored(self) -> None:
        assert glob_matches("a.py", "  *.py \n")

    def test_pattern_with_slash_is_anchored_without_leading_double_star(self) -> None:
        assert not glob_matches("lib/src/a.py", "src/*.py")

    def test_dots_are_literal(self) -> None:
        assert glob_matches("a.py", "a.py")
        assert not glob_matches("abpy", "a.py")


class TestBraces:
    def test_alternatives(self) -> None:
        assert glob_matches("a.py", "*.{py,ts}")
        assert glob_matches("a.ts", "*.{py,ts}")
        assert not glob_matches("a.js", "*.{py,ts}")

    def test_alternatives_with_path_segments(self) -> None:
        assert glob_matches("src/pkg/a.py", "src/{pkg,util}/*.py")
        assert glob_matches("src/util/a.py", "src/{pkg,util}/*.py")
        assert not glob_matches("src/other/a.py", "src/{pkg,util}/*.py")

    def test_nested_alternatives(self) -> None:
        assert glob_matches("a.py", "{a,b{1,2}}.py")
        assert glob_matches("b2.py", "{a,b{1,2}}.py")
        assert not glob_matches("b3.py", "{a,b{1,2}}.py")

    def test_multiple_groups(self) -> None:
        assert glob_matches("src/a.py", "{src,lib}/{a,b}.{py,ts}")
        assert glob_matches("lib/b.ts", "{src,lib}/{a,b}.{py,ts}")
        assert not glob_matches("lib/c.ts", "{src,lib}/{a,b}.{py,ts}")

    def test_group_without_comma_is_literal(self) -> None:
        assert glob_matches("{x}.txt", "{x}.txt")
        assert not glob_matches("x.txt", "{x}.txt")

    def test_empty_alternative(self) -> None:
        assert glob_matches("a", "a{,.py}")
        assert glob_matches("a.py", "a{,.py}")

    def test_unbalanced_brace_is_literal(self) -> None:
        assert glob_matches("{a.py", "{a.py")

    def test_expansion_limit(self) -> None:
        with pytest.raises(ValueError, match="too many"):
            compile_glob("{a,b}" * 8)


class TestValidation:
    @pytest.mark.parametrize("pattern", ["", "   ", "./", "a\x00b"])
    def test_rejects(self, pattern: str) -> None:
        with pytest.raises(ValueError):
            compile_glob(pattern)

    def test_compile_is_cached(self) -> None:
        assert compile_glob("src/**/*.py") is compile_glob("src/**/*.py")


class TestNormalize:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("./src/*.py", "src/*.py"), ("  *.py \n", "*.py"), ("src/*.py", "src/*.py"), ("/a.py", "/a.py")],
    )
    def test_normalize_glob(self, raw: str, expected: str) -> None:
        assert normalize_glob(raw) == expected


class TestStackedWildcards:
    """Matching runs on the server's event loop, so stacked wildcards must not cost more than milliseconds."""

    @pytest.mark.parametrize(
        ("pattern", "path"),
        [
            ("**/a/" * 4 + "**/b", "/".join(["a"] * 127)),
            ("**/a/" * 3 + "**/b", "/".join(["a"] * 120) + "/b/a"),
            ("*a" * 4 + "*b", "a" * 120 + "c"),
        ],
        ids=["stacked-double-star", "literal-present-but-misplaced", "many-stars-in-one-segment"],
    )
    def test_evaluation_is_fast(self, pattern: str, path: str) -> None:
        started = time.perf_counter()
        assert not glob_matches(path, pattern)
        assert time.perf_counter() - started < 0.1


class TestMatchAll:
    @pytest.mark.parametrize("pattern", ["*", "**", "**/*", "**/**"])
    def test_match_all_spellings(self, pattern: str) -> None:
        assert is_match_all(pattern)

    @pytest.mark.parametrize("pattern", ["*.py", "**/*.py", "src/*", "", "/*"])
    def test_specific_patterns(self, pattern: str) -> None:
        assert not is_match_all(pattern)


def _ripgrep_matches(root: Path, pattern: str) -> set[str]:
    completed = subprocess.run(
        ["rg", "--files", "--hidden", "--no-ignore", "--no-messages", "--glob", normalize_glob(pattern), "."],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return {line.removeprefix("./") for line in completed.stdout.splitlines() if line}


@pytest.fixture(scope="module")
def parity_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("glob_parity")
    for relative in TREE_FILES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")
    return root


@pytest.mark.usefixtures("require_ripgrep")
class TestRipgrepParity:
    """The Python tier and the ripgrep tier must select the same files for the same pattern."""

    @pytest.mark.parametrize("pattern", PARITY_PATTERNS)
    def test_same_selection_as_ripgrep(self, parity_tree: Path, pattern: str) -> None:
        tree = parity_tree
        expected = _ripgrep_matches(tree, pattern)
        actual = {path for path in TREE_FILES if glob_matches(path, pattern)}
        assert actual == expected
