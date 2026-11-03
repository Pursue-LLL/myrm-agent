"""Python-tier content search for grep_tool.

[INPUT]
- mmap (POS: memory-mapped line scan that never loads a whole file)
- regex_validator::RegexValidator (POS: 正则表达式验证器，防止 ReDoS；safe_search 为单行匹配加时间上限)
- utils.errors::ToolError (POS: Tool error carrying a user-facing hint)

[OUTPUT]
- scan_lines: Match the lines of a byte stream the way ripgrep does and add context rows; shared by both read paths
- mmap_search_file: Search one file and return its matching lines
- search_files: Search candidate files in concurrent batches under a wall-clock budget

[POS]
Content search used when ripgrep is unavailable or fails. Receives the candidate files that
``fallback_discovery`` selected, so it never decides which files are searched, only how: skip known binary
suffixes, scan with mmap, fall back to a plain read, stop at the result cap or the time budget. A line is
numbered and matched the way ripgrep does (only a line feed ends a line, and the line ending is not part of the
text a pattern sees), and a match carries the same context rows, so a pattern means the same on both tiers.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import mmap
import re
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.errors import ToolError

if TYPE_CHECKING:
    from .regex_validator import RegexValidator

logger = logging.getLogger(__name__)

_BINARY_SUFFIXES = frozenset({".pyc", ".so", ".dll", ".exe", ".bin", ".jpg", ".png", ".gif", ".pdf", ".zip"})
_BATCH_SIZE = 20


def scan_lines(
    lines: Iterable[bytes],
    matches: Callable[[str], object],
    max_matches: int,
    context_lines: int,
) -> Iterator[dict[str, str | int]]:
    """Yield the rows of ``lines`` (raw, line-feed terminated) that ``matches`` accepts, with their context rows.

    A line is matched without its line feed and nothing else, so ``$`` and trailing whitespace behave as they do
    in ripgrep. Lines that are not UTF-8 are skipped but still numbered, and the scan ends at the
    ``max_matches``-th match without trailing context.
    """
    before: deque[tuple[int, str]] = deque(maxlen=context_lines)
    after_left = 0
    match_count = 0
    for number, raw in enumerate(lines, 1):
        try:
            line = raw.decode("utf-8").rstrip("\n")
        except UnicodeDecodeError:
            continue
        if matches(line):
            for context_number, context_line in before:
                yield {"line": context_number, "content": context_line.rstrip(), "type": "context"}
            before.clear()
            yield {"line": number, "content": line.rstrip(), "type": "match"}
            match_count += 1
            if match_count >= max_matches:
                return
            after_left = context_lines
        elif after_left:
            after_left -= 1
            yield {"line": number, "content": line.rstrip(), "type": "context"}
        elif context_lines:
            before.append((number, line))


def mmap_search_file(
    file: Path,
    regex: re.Pattern[str],
    max_matches: int = 50,
    context_lines: int = 0,
) -> list[dict[str, str | int]]:
    """Search one file through a memory map, which never loads the whole file."""
    rows: list[dict[str, str | int]] = []
    try:
        with open(file, "rb") as f:
            # An empty file cannot be mapped.
            if f.seek(0, 2) == 0:
                return rows
            f.seek(0)
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                rows.extend(scan_lines(iter(mm.readline, b""), regex.search, max_matches, context_lines))
    except (OSError, ValueError):
        # A file that cannot be mapped (permissions, special files) keeps whatever matched before the failure.
        pass
    return rows


async def _scan_by_reading(
    file: Path,
    regex: re.Pattern[str],
    regex_validator: RegexValidator,
    max_matches: int,
    context_lines: int,
) -> list[dict[str, str | int]]:
    """Slow path for a file mmap failed on: read it whole and match each line under the regex time limit."""
    data = await asyncio.to_thread(file.read_bytes)
    rows: list[dict[str, str | int]] = []
    # A line that exhausts the time limit ends the scan of this file and keeps the rows found before it.
    with contextlib.suppress(ToolError):
        rows.extend(
            scan_lines(
                iter(io.BytesIO(data).readline, b""),
                partial(regex_validator.safe_search, regex),
                max_matches,
                context_lines,
            )
        )
    return rows


async def _search_file(
    file: Path,
    regex: re.Pattern[str],
    search_root: Path,
    regex_validator: RegexValidator,
    max_results: int,
    context_lines: int,
) -> list[dict[str, str | int]]:
    if file.suffix in _BINARY_SUFFIXES:
        return []

    try:
        rel_path = file.relative_to(search_root)
    except ValueError:
        rel_path = file

    try:
        try:
            rows = await asyncio.to_thread(mmap_search_file, file, regex, max_results, context_lines)
        except Exception:
            rows = await _scan_by_reading(file, regex, regex_validator, max_results, context_lines)
    except OSError:
        return []
    return [{**row, "file": str(rel_path)} for row in rows]


async def search_files(
    files: list[Path],
    regex: re.Pattern[str],
    search_root: Path,
    *,
    regex_validator: RegexValidator,
    max_results: int,
    timeout_seconds: float,
    context_lines: int = 0,
) -> tuple[list[dict[str, str | int]], int]:
    """Search ``files`` for ``regex``; returns the rows and how many files were reached.

    Files are searched ``_BATCH_SIZE`` at a time. The loop stops once ``max_results`` matches are collected
    (context rows do not count) or ``timeout_seconds`` have elapsed, so the second value can be smaller than
    ``len(files)``. Paths in the rows are relative to ``search_root``.
    """
    results: list[dict[str, str | int]] = []
    match_count = 0
    start_time = time.time()
    start = 0
    batch: list[Path] = []

    for start in range(0, len(files), _BATCH_SIZE):
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            logger.warning(f"Search timeout after {elapsed:.1f}s")
            break
        batch = files[start : start + _BATCH_SIZE]
        batch_results = await asyncio.gather(
            *[_search_file(file, regex, search_root, regex_validator, max_results, context_lines) for file in batch]
        )
        for file_results in batch_results:
            results.extend(file_results)
            match_count += sum(1 for row in file_results if row["type"] == "match")
            if match_count >= max_results:
                break
        if match_count >= max_results:
            break

    return results, min(start + len(batch), len(files))
