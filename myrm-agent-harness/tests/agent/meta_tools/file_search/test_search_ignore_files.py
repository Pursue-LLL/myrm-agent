"""End-to-end tests: ignore files in a folder without ``.git`` apply directory by directory, once per search tier.

ripgrep is the reference. A file is listed when the ignore files from the search root down to its directory leave it
visible: within one kind the deepest file with an opinion decides, and ``.rgignore`` outranks ``.ignore``, which
outranks ``.gitignore``.

Covers:
- An ignore file in a subdirectory hides what it names below that directory only, and a deeper one takes a file back
- ``.ignore`` and ``.rgignore`` apply in subdirectories; a higher ranked kind wins over a deeper file of a lower kind
- A directory that a negated directory pattern takes back is searched
- What an ignored directory holds does not use up the result cap
- ``include_ignored`` reads no ignore file at any depth
- Patterns are read as written: leading blanks and an escaped trailing blank count (both tiers)
- The Python tier drops a leading byte order mark, skips a file it cannot read or compile with a warning, and keeps
  searching, unfiltered, when ``pathspec`` is missing
- An ignore file that is not a regular file (a FIFO) does not stall discovery
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_search import fallback_discovery
from myrm_agent_harness.agent.meta_tools.file_search.fallback_discovery import collect_candidate_files
from tests.agent.meta_tools.file_search.search_probe import SearchRunner, hit_files, listed, warnings_from, write_tree


class TestSubdirectoryIgnoreFiles:
    async def test_hide_what_they_name_below_their_directory_only(
        self, plain_dir: Path, run_glob: SearchRunner, run_grep: SearchRunner
    ) -> None:
        write_tree(
            plain_dir,
            {
                "pkg/.gitignore": "generated/\n*.tmp\n",
                "pkg/mod.py": "needle\n",
                "pkg/generated/out.py": "needle\n",
                "pkg/x.tmp": "needle\n",
                "other/generated/keep.py": "needle\n",
                "other/y.tmp": "needle\n",
                "top.tmp": "needle\n",
            },
        )
        searched = {"pkg/mod.py", "other/generated/keep.py", "other/y.tmp", "top.tmp"}

        assert listed(await run_glob(plain_dir, "**/*")) == searched | {"pkg/.gitignore"}
        output = await run_grep(plain_dir, "needle")
        assert hit_files(output, searched | {"pkg/generated/out.py", "pkg/x.tmp"}) == searched

    async def test_a_deeper_file_takes_back_what_a_shallower_one_hides(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(
            plain_dir,
            {
                ".gitignore": "*.log\n",
                "a.log": "x\n",
                "sub/.gitignore": "!keep.log\n",
                "sub/keep.log": "x\n",
                "sub/drop.log": "x\n",
                "sub/deeper/keep.log": "x\n",
            },
        )

        assert listed(await run_glob(plain_dir, "**/*")) == {
            ".gitignore",
            "sub/.gitignore",
            "sub/keep.log",
            "sub/deeper/keep.log",
        }

    async def test_ignore_and_rgignore_files_apply_in_subdirectories(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(
            plain_dir,
            {
                "a/.ignore": "by_ignore.txt\n",
                "a/by_ignore.txt": "x\n",
                "a/shown.txt": "x\n",
                "b/.rgignore": "by_rgignore.txt\n",
                "b/by_rgignore.txt": "x\n",
                "b/by_ignore.txt": "x\n",
            },
        )

        assert listed(await run_glob(plain_dir, "**/*")) == {
            "a/.ignore",
            "a/shown.txt",
            "b/.rgignore",
            "b/by_ignore.txt",
        }

    async def test_kinds_rank_rgignore_over_ignore_over_gitignore(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(
            plain_dir,
            {
                ".gitignore": "*.txt\n",
                ".ignore": "!a.txt\nb.txt\n!d.txt\n",
                ".rgignore": "!b.txt\nd.txt\n",
                "a.txt": "x\n",
                "b.txt": "x\n",
                "c.txt": "x\n",
                "d.txt": "x\n",
            },
        )

        assert listed(await run_glob(plain_dir, "**/*")) == {".gitignore", ".ignore", ".rgignore", "a.txt", "b.txt"}

    async def test_a_higher_ranked_kind_wins_over_a_deeper_file_of_a_lower_kind(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(
            plain_dir,
            {
                ".rgignore": "x.txt\n",
                "x.txt": "x\n",
                "sub/.gitignore": "!x.txt\n",
                "sub/x.txt": "x\n",
                "sub/y.txt": "x\n",
            },
        )

        assert listed(await run_glob(plain_dir, "**/*")) == {".rgignore", "sub/.gitignore", "sub/y.txt"}

    async def test_a_directory_that_a_negated_directory_pattern_takes_back_is_searched(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(
            plain_dir,
            {
                ".gitignore": "/docs/*\n!/docs/next/\n",
                "docs/old/a.md": "x\n",
                "docs/next/b.md": "x\n",
                "docs/top.md": "x\n",
            },
        )

        assert listed(await run_glob(plain_dir, "**/*")) == {".gitignore", "docs/next/b.md"}


class TestResultCapAndIncludeIgnored:
    async def test_an_ignored_directory_does_not_use_up_the_result_cap(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        junk = {f"module/target/t{number}.class": "x\n" for number in range(30)}
        write_tree(plain_dir, {"module/.gitignore": "target/\n", "module/src/Main.java": "x\n", "z.txt": "x\n", **junk})

        listing = listed(await run_glob(plain_dir, "**/*", max_results=5))

        assert listing == {"module/.gitignore", "module/src/Main.java", "z.txt"}

    async def test_include_ignored_lists_what_ignore_files_hide_at_every_depth(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        files = {
            ".gitignore": "*.log\n",
            "a.log": "x\n",
            "sub/.gitignore": "generated/\n",
            "sub/generated/out.py": "x\n",
            "sub/ok.py": "x\n",
        }
        write_tree(plain_dir, files)

        assert listed(await run_glob(plain_dir, "**/*", include_ignored=True)) == set(files)


@pytest.mark.skipif(sys.platform == "win32", reason="a file name cannot end in a blank on Windows")
class TestPatternsAreReadAsWritten:
    async def test_leading_blanks_belong_to_the_pattern(self, plain_dir: Path, run_glob: SearchRunner) -> None:
        # ``" *.tmp"`` names files that start with a blank, so it does not hide ``a.tmp``.
        write_tree(plain_dir, {".gitignore": " *.tmp\n", "a.tmp": "x\n"})

        assert listed(await run_glob(plain_dir, "**/*")) == {".gitignore", "a.tmp"}

    async def test_an_escaped_trailing_blank_belongs_to_the_pattern(
        self, plain_dir: Path, run_glob: SearchRunner
    ) -> None:
        write_tree(plain_dir, {".gitignore": "hide\\ \n", "hide ": "x\n", "keep.txt": "x\n"})

        assert listed(await run_glob(plain_dir, "**/*")) == {".gitignore", "keep.txt"}


@pytest.mark.parametrize("engine", ["python"], indirect=True)
class TestPythonTierReadsIgnoreFiles:
    async def test_a_leading_byte_order_mark_is_dropped(self, plain_dir: Path, run_glob: SearchRunner) -> None:
        write_tree(plain_dir, {"a.tmp": "x\n", "b.py": "x\n"})
        (plain_dir / ".gitignore").write_bytes(b"\xef\xbb\xbf*.tmp\n")

        assert listed(await run_glob(plain_dir, "**/*")) == {".gitignore", "b.py"}

    async def test_a_file_that_cannot_be_compiled_is_skipped_with_a_warning(
        self, plain_dir: Path, run_glob: SearchRunner, caplog: pytest.LogCaptureFixture
    ) -> None:
        # ``[z-a]`` is an invalid range; ripgrep skips that line and honours ``*.log``, the Python tier skips the file.
        write_tree(
            plain_dir,
            {
                ".gitignore": "*.tmp\n",
                "sub/.gitignore": "[z-a]\n*.log\n",
                "a.tmp": "x\n",
                "sub/b.tmp": "x\n",
                "sub/c.log": "x\n",
            },
        )

        assert listed(await run_glob(plain_dir, "**/*")) == {".gitignore", "sub/.gitignore", "sub/c.log"}
        [message] = warnings_from(caplog, fallback_discovery)
        assert str(plain_dir / "sub" / ".gitignore") in message

    async def test_a_file_that_cannot_be_read_is_skipped_with_a_warning(
        self,
        plain_dir: Path,
        run_glob: SearchRunner,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        write_tree(plain_dir, {".gitignore": "*.tmp\n", "a.tmp": "x\n"})
        real_read_text = Path.read_text

        def deny_ignore_files(path: Path, encoding: str | None = None, errors: str | None = None) -> str:
            if path.name == ".gitignore":
                raise PermissionError(13, "Permission denied", str(path))
            return real_read_text(path, encoding=encoding, errors=errors)

        monkeypatch.setattr(Path, "read_text", deny_ignore_files)

        assert listed(await run_glob(plain_dir, "**/*")) == {".gitignore", "a.tmp"}
        [message] = warnings_from(caplog, fallback_discovery)
        assert "Cannot read ignore file" in message

    async def test_a_build_without_pathspec_searches_unfiltered(
        self, plain_dir: Path, run_glob: SearchRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_tree(plain_dir, {".gitignore": "*.tmp\n", "a.tmp": "x\n", "b.py": "x\n"})
        monkeypatch.setitem(sys.modules, "pathspec", None)

        assert listed(await run_glob(plain_dir, "**/*")) == {".gitignore", "a.tmp", "b.py"}


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs need a POSIX system")
class TestIgnoreFileThatIsNotARegularFile:
    @pytest.mark.parametrize("location", [".", "sub"])
    def test_does_not_stall_discovery(self, plain_dir: Path, location: str) -> None:
        write_tree(plain_dir, {"a.txt": "x\n", "sub/b.txt": "x\n"})
        fifo = plain_dir / location / ".gitignore"
        os.mkfifo(fifo)
        found: list[list[Path]] = []

        def discover() -> None:
            found.append(
                collect_candidate_files(
                    search_root=plain_dir, file_pattern="**/*", max_files=100, include_ignored=False
                )
            )

        # A daemon thread: opening a FIFO for reading blocks until a writer appears.
        worker = threading.Thread(target=discover, daemon=True)
        worker.start()
        worker.join(timeout=5)
        stalled = worker.is_alive()
        if stalled:
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))  # lets the blocked read finish
            worker.join(timeout=5)

        assert not stalled, "discovery blocked on an ignore file that is a FIFO"
        assert {path.name for path in found[0]} == {"a.txt", "b.txt"}
