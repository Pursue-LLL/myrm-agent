#!/usr/bin/env python3
"""Profile peak RSS per test file to find memory-heavy tests."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    path: str
    peak_rss_mb: float
    exit_code: int
    summary: str


def _parse_peak_rss_mb(stderr: str) -> float:
    # macOS: "maximum resident set size" in bytes
    match = re.search(r"(\d+)\s+maximum resident set size", stderr)
    if match:
        return int(match.group(1)) / (1024 * 1024)
    # Linux GNU time: "Maximum resident set size (kbytes):"
    match = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", stderr)
    if match:
        return int(match.group(1)) / 1024
    return 0.0


def _run_one(server_root: Path, test_file: Path, timeout_s: int, parallel: bool) -> RunResult:
    addopts = "-q --timeout=300"
    if parallel:
        addopts = "-n auto --timeout=300 -q"
    cmd = [
        "uv",
        "run",
        "pytest",
        str(test_file),
        "-o",
        f"addopts={addopts}",
        "--tb=no",
        "--maxfail=1",
    ]
    proc = subprocess.run(
        ["/usr/bin/time", "-l", *cmd],
        cwd=str(server_root),
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr
    summary = ""
    for line in out.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            if "==" in line or "passed" in line:
                summary = line.strip()
                break
    if not summary:
        summary = out[-300:].replace("\n", " ")
    return RunResult(
        path=str(test_file.relative_to(server_root)),
        peak_rss_mb=round(_parse_peak_rss_mb(proc.stderr), 1),
        exit_code=proc.returncode,
        summary=summary,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="Test files or directories")
    parser.add_argument("--parallel", action="store_true", help="Run with pytest-xdist -n auto")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    server_root = Path(__file__).resolve().parents[2]
    if not args.paths:
        targets = [
            server_root / "tests" / "e2e",
            server_root / "tests" / "api" / "agent",
            server_root / "tests" / "e2e" / "test_docker_persistence_e2e.py",
        ]
    else:
        targets = [server_root / p for p in args.paths]

    test_files: list[Path] = []
    for target in targets:
        if target.is_file():
            test_files.append(target)
        elif target.is_dir():
            test_files.extend(sorted(target.glob("test_*.py")))

    results: list[RunResult] = []
    for test_file in test_files:
        print(f"Profiling {test_file.name}...", file=sys.stderr)
        results.append(_run_one(server_root, test_file, args.timeout, args.parallel))

    results.sort(key=lambda r: r.peak_rss_mb, reverse=True)
    print(f"\n{'PEAK_MB':>8}  {'EXIT':>4}  FILE")
    print("-" * 72)
    for row in results[: args.top]:
        print(f"{row.peak_rss_mb:8.1f}  {row.exit_code:4d}  {row.path}")
        if row.peak_rss_mb >= 500 or row.exit_code != 0:
            print(f"          {row.summary[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
