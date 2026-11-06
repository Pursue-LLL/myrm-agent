"""Tests for grep_tool: its input schema and the two search engines behind it.

Covers:
- GrepInput defaults and custom values
- ripgrep detection: whether `rg` is on the PATH, looked up on every call
- ripgrep search engine (tier 1)
- mmap search engine (tier 2)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.file_search.fallback_search import mmap_search_file
from myrm_agent_harness.agent.meta_tools.file_search.grep_tool import (
    GrepInput,
    _has_ripgrep,
    _ripgrep_search,
)

# ---------------------------------------------------------------------------
# Tests: GrepInput schema
# ---------------------------------------------------------------------------


class TestGrepInput:
    def test_defaults(self) -> None:
        inp = GrepInput(pattern="test")
        assert inp.path == "."
        assert inp.file_pattern == "**/*"
        assert inp.ignore_case is False

    def test_custom_values(self) -> None:
        inp = GrepInput(pattern="def", path="src", file_pattern="**/*.py", ignore_case=True)
        assert inp.pattern == "def"
        assert inp.path == "src"
        assert inp.file_pattern == "**/*.py"
        assert inp.ignore_case is True


# ---------------------------------------------------------------------------
# Tests: ripgrep detection
# ---------------------------------------------------------------------------


class TestRipgrepDetection:
    def test_follows_the_path_on_every_call(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """PATH changes under a running process (a host completing it after startup, ripgrep installed meanwhile)."""
        monkeypatch.setenv("PATH", str(tmp_path))
        ripgrep = tmp_path / ("rg.exe" if sys.platform == "win32" else "rg")

        assert _has_ripgrep() is False
        ripgrep.write_text("")
        ripgrep.chmod(0o755)
        assert _has_ripgrep() is True
        ripgrep.unlink()
        assert _has_ripgrep() is False


# ---------------------------------------------------------------------------
# Tests: mmap search
# ---------------------------------------------------------------------------


class TestMmapSearch:
    def test_search_finds_match(self, workspace: Path) -> None:
        import re

        regex = re.compile("def hello")
        results = mmap_search_file(workspace / "hello.py", regex)
        assert len(results) == 1
        assert results[0]["line"] == 1
        assert "def hello" in str(results[0]["content"])

    def test_search_empty_file(self, workspace: Path) -> None:
        import re

        regex = re.compile("anything")
        results = mmap_search_file(workspace / "empty.txt", regex)
        assert results == []

    def test_search_max_matches(self, workspace: Path) -> None:
        import re

        many_lines = workspace / "many.txt"
        many_lines.write_text("\n".join(f"match line {i}" for i in range(100)))
        regex = re.compile("match")
        results = mmap_search_file(many_lines, regex, max_matches=5)
        assert len(results) == 5

    def test_search_nonexistent_file(self, workspace: Path) -> None:
        import re

        regex = re.compile("test")
        results = mmap_search_file(workspace / "nonexistent.py", regex)
        assert results == []

    def test_search_binary_like_content(self, workspace: Path) -> None:
        import re

        bin_file = workspace / "data.bin"
        bin_file.write_bytes(b"\x00\x01\x02\xff\xfe")
        regex = re.compile("test")
        results = mmap_search_file(bin_file, regex)
        assert results == []

    def test_search_multiple_matches_in_file(self, workspace: Path) -> None:
        import re

        regex = re.compile("def")
        results = mmap_search_file(workspace / "hello.py", regex)
        assert len(results) == 2
        assert results[0]["line"] == 1
        assert results[1]["line"] == 4


# ---------------------------------------------------------------------------
# Tests: ripgrep search engine
# ---------------------------------------------------------------------------


class TestRipgrepSearch:
    async def test_basic_search(self, workspace: Path, require_ripgrep: None) -> None:
        results = (await _ripgrep_search("def", workspace, "**/*", False, 0, 100)).rows
        assert len(results) >= 2
        files = {r["file"] for r in results}
        assert any("hello.py" in str(f) for f in files)

    async def test_ignore_case(self, workspace: Path, require_ripgrep: None) -> None:
        (workspace / "case.txt").write_text("Hello\nHELLO\nhello\n")
        results = (await _ripgrep_search("hello", workspace, "**/*", True, 0, 100)).rows
        assert len(results) >= 3

    async def test_file_pattern_filter(self, workspace: Path, require_ripgrep: None) -> None:
        results = (await _ripgrep_search("import", workspace, "**/*.py", False, 0, 100)).rows
        for r in results:
            assert str(r["file"]).endswith(".py")

    async def test_max_results_limit(self, workspace: Path, require_ripgrep: None) -> None:
        many = workspace / "big.py"
        many.write_text("\n".join(f"match_{i} = True" for i in range(200)))
        results = (await _ripgrep_search("match_", workspace, "**/*", False, 0, 5)).rows
        assert len(results) <= 5

    async def test_no_match_returns_empty(self, workspace: Path, require_ripgrep: None) -> None:
        results = (await _ripgrep_search("NONEXISTENT_STRING_12345", workspace, "**/*", False, 0, 100)).rows
        assert results == []

    async def test_nonzero_returncode_raises_runtime_error_without_name_error(self, workspace: Path) -> None:
        class _FakeStdout:
            async def readuntil(self, _separator: bytes) -> bytes:
                raise asyncio.IncompleteReadError(b"", None)  # end of stream with nothing buffered

        class _FakeStderr:
            def __init__(self) -> None:
                self._sent = False

            async def read(self, _: int) -> bytes:
                if self._sent:
                    return b""
                self._sent = True
                return b"simulated error"

        class _FakeProcess:
            def __init__(self) -> None:
                self.stdout = _FakeStdout()
                self.stderr = _FakeStderr()
                self.returncode = 2
                self.terminated = False

            async def wait(self) -> int:
                return self.returncode

            def terminate(self) -> None:
                self.terminated = True

        fake_proc = _FakeProcess()
        with (
            patch(
                "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.asyncio.create_subprocess_exec",
                return_value=fake_proc,
            ),
            pytest.raises(RuntimeError, match="exit code 2: simulated error"),
        ):
            await _ripgrep_search("pattern", workspace, "**/*", False, 0, 10)
