#!/usr/bin/env python3
"""Fail CI when new Python modules exceed the line budget (default 400 lines).

Uses a baseline file listing app-relative paths that already exceed the budget.
PRs may not add new offenders; shrinking the baseline is allowed.

Run from myrm-agent-server root::

    python3 scripts/check_file_line_budget.py
    python3 scripts/check_file_line_budget.py --write-baseline

Exit codes:
    0  All files within budget or listed in baseline.
    1  One or more new offenders found.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DEFAULT_MAX_LINES = 400
_DEFAULT_BASELINE = Path(__file__).resolve().parent / "ci" / "file_line_budget_baseline.txt"
_PRUNE = frozenset({"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"})


def _iter_py_files(app_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(app_root.rglob("*.py")):
        if any(part in _PRUNE for part in path.parts):
            continue
        files.append(path)
    return files


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _load_baseline(path: Path) -> frozenset[str]:
    if not path.is_file():
        return frozenset()
    entries: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.add(stripped)
    return frozenset(entries)


def _write_baseline(path: Path, offenders: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(sorted(offenders))
    path.write_text(f"# app-relative Python paths over budget (auto-generated)\n{body}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "app",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=_DEFAULT_MAX_LINES,
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_DEFAULT_BASELINE,
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Rewrite baseline from current offenders (maintainer only).",
    )
    args = parser.parse_args(argv)

    app_root: Path = args.app_root.resolve()
    offenders: list[str] = []
    for py in _iter_py_files(app_root):
        count = _line_count(py)
        if count > args.max_lines:
            rel = str(py.relative_to(app_root.parent))
            offenders.append(rel)

    if args.write_baseline:
        _write_baseline(args.baseline.resolve(), offenders)
        print(f"Wrote baseline ({len(offenders)} paths) to {args.baseline}")
        return 0

    baseline = _load_baseline(args.baseline.resolve())
    new_offenders = sorted(path for path in offenders if path not in baseline)
    if new_offenders:
        print("ERROR: New Python files exceed line budget:", file=sys.stderr)
        for path in new_offenders:
            full = app_root.parent / path
            print(f"  - {path} ({_line_count(full)} lines, max {args.max_lines})", file=sys.stderr)
        print(
            f"Fix by splitting the module or, if unavoidable, update {args.baseline.name} via --write-baseline.",
            file=sys.stderr,
        )
        return 1

    print(f"OK (line budget {args.max_lines}, baseline {len(baseline)} grandfathered).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
