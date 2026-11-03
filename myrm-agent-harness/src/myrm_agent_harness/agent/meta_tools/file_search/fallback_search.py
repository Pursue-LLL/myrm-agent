"""Python-tier content search for grep_tool.

[INPUT]
- mmap (POS: memory-mapped line scan that never loads a whole file)
- regex_validator::RegexValidator (POS: 正则表达式验证器，防止 ReDoS；safe_search 为单行匹配加时间上限)
- utils.errors::ToolError (POS: Tool error carrying a user-facing hint)

[OUTPUT]
- mmap_search_file: Search one file and return its matching lines
- search_files: Search candidate files in concurrent batches under a wall-clock budget

[POS]
Content search used when ripgrep is unavailable or fails. Receives the candidate files that
``fallback_discovery`` selected, so it never decides which files are searched, only how: skip known binary
suffixes, scan with mmap, fall back to a plain read, stop at the result cap or the time budget.
"""

from __future__ import annotations

import asyncio
import logging
import mmap
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.errors import ToolError

if TYPE_CHECKING:
    from .regex_validator import RegexValidator

logger = logging.getLogger(__name__)

_BINARY_SUFFIXES = frozenset({".pyc", ".so", ".dll", ".exe", ".bin", ".jpg", ".png", ".gif", ".pdf", ".zip"})
_BATCH_SIZE = 20


def mmap_search_file(file: Path, regex: re.Pattern[str], max_matches: int = 50) -> list[dict[str, str | int]]:
    """使用 mmap 搜索单个文件（内存高效）"""
    results: list[dict[str, str | int]] = []
    try:
        with open(file, "rb") as f:
            # 空文件直接跳过
            if f.seek(0, 2) == 0:
                return results
            f.seek(0)

            # 使用 mmap（内存映射，不加载整个文件）
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                # 逐行扫描（mmap 支持迭代）
                line_num = 0
                for line_bytes in iter(mm.readline, b""):
                    line_num += 1
                    try:
                        line = line_bytes.decode("utf-8").rstrip()
                        if regex.search(line):
                            results.append({"line": line_num, "content": line})
                            if len(results) >= max_matches:
                                break
                    except UnicodeDecodeError:
                        continue

    except (OSError, ValueError):
        # mmap 失败（如空文件、权限问题），fallback 到普通读取
        pass

    return results


async def _search_file(
    file: Path,
    regex: re.Pattern[str],
    search_root: Path,
    regex_validator: RegexValidator,
    max_results: int,
) -> list[dict[str, str | int]]:
    file_results: list[dict[str, str | int]] = []
    if file.suffix in _BINARY_SUFFIXES:
        return file_results

    try:
        rel_path = file.relative_to(search_root)
    except ValueError:
        rel_path = file

    try:
        try:
            file_matches = await asyncio.to_thread(mmap_search_file, file, regex, max_results)
            for match in file_matches:
                file_results.append({"file": str(rel_path), "line": match["line"], "content": match["content"]})
        except Exception:
            content = await asyncio.to_thread(file.read_text, encoding="utf-8")
            for line_num, line in enumerate(content.splitlines(), 1):
                try:
                    if regex_validator.safe_search(regex, line):
                        file_results.append({"file": str(rel_path), "line": line_num, "content": line.rstrip()})
                        if len(file_results) >= max_results:
                            break
                except ToolError:
                    break
    except (UnicodeDecodeError, PermissionError, OSError):
        pass
    return file_results


async def search_files(
    files: list[Path],
    regex: re.Pattern[str],
    search_root: Path,
    *,
    regex_validator: RegexValidator,
    max_results: int,
    timeout_seconds: float,
) -> tuple[list[dict[str, str | int]], int]:
    """Search ``files`` for ``regex``; returns the matches and how many files were reached.

    Files are searched ``_BATCH_SIZE`` at a time. The loop stops once ``max_results`` matches are collected or
    ``timeout_seconds`` have elapsed, so the second value can be smaller than ``len(files)``. Paths in the
    matches are relative to ``search_root``.
    """
    results: list[dict[str, str | int]] = []
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
            *[_search_file(file, regex, search_root, regex_validator, max_results) for file in batch]
        )
        for file_results in batch_results:
            results.extend(file_results)
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    return results, min(start + len(batch), len(files))
