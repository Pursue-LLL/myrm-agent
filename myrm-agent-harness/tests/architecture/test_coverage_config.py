"""Coverage exclusion patterns must not hide real code.

coverage.py drops a whole function from the measurement when any line of its ``def``
header matches an ``exclude_lines`` pattern. A pattern that matches ``...`` anywhere in a
line would therefore hide every function whose signature mentions ``tuple[str, ...]`` or
``Callable[..., T]``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _is_excluded(line: str) -> bool:
    config = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    patterns = config["tool"]["coverage"]["report"]["exclude_lines"]
    return any(re.search(pattern, line) for pattern in patterns)


@pytest.mark.architecture
@pytest.mark.parametrize("line", ["...", "    ...", "        ...   "])
def test_a_stub_body_that_is_only_an_ellipsis_is_excluded(line: str) -> None:
    assert _is_excluded(line)


@pytest.mark.architecture
@pytest.mark.parametrize(
    "line",
    [
        "    recent_tool_calls: tuple[RecentToolCall, ...] = (),",
        "def load_repo_command_prefixes(workspace_root: str) -> tuple[str, ...]:",
        "    handler: Callable[..., Awaitable[None]],",
        '    args_str = args_str[:500] + "..."',
    ],
)
def test_an_ellipsis_inside_a_line_does_not_exclude_it(line: str) -> None:
    assert not _is_excluded(line)
