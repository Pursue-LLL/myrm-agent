#!/usr/bin/env python3
"""Fail CI when TypeScript strict error count exceeds baseline.

Run from myrm-agent-frontend root::

    python3 scripts/check_typescript_strict.py
    python3 scripts/check_typescript_strict.py --write-baseline
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_DEFAULT_BASELINE = Path(__file__).resolve().parent / "ci" / "typescript_strict_baseline.txt"
_ERROR_RE = re.compile(r"error TS\d+")


def _run_tsc(frontend_root: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["bunx", "tsc", "--noEmit"],
        cwd=frontend_root,
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    count = len(_ERROR_RE.findall(output))
    return count, output


def _load_baseline_max(path: Path) -> int | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return int(stripped)
    return None


def _write_baseline(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# tsc --noEmit strict error count (auto-generated)\n{count}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=_DEFAULT_BASELINE)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)

    frontend_root = Path(__file__).resolve().parent.parent
    count, output = _run_tsc(frontend_root)

    if args.write_baseline:
        _write_baseline(args.baseline.resolve(), count)
        print(f"Wrote baseline ({count} errors) to {args.baseline}")
        return 0

    baseline_max = _load_baseline_max(args.baseline.resolve())
    if baseline_max is None:
        print("ERROR: Missing typescript strict baseline. Run with --write-baseline.", file=sys.stderr)
        return 1

    if count > baseline_max:
        print(
            f"ERROR: TypeScript strict errors increased: {count} (baseline max {baseline_max}).",
            file=sys.stderr,
        )
        print(output[-4000:], file=sys.stderr)
        return 1

    if count < baseline_max:
        print(
            f"OK (strict errors {count}, baseline {baseline_max}). "
            f"Shrink baseline via --write-baseline when intentional.",
        )
        return 0

    print(f"OK (strict errors {count}, baseline {baseline_max}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
