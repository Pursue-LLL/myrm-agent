#!/usr/bin/env python3
"""Fractal self-documentation gate for myrm-agent-frontend.

Tier 1 (``--strict-roots``): module roots and ``src/components/features/*`` top-level
feature folders must have ``_ARCH.md`` (no baseline).

Tier 2 (default recursive scan): directories under configured roots that contain
``.ts`` / ``.tsx`` source (excluding tests) must have ``_ARCH.md`` or a baseline entry.

Exit codes:
    0  All checks passed.
    2  Strict roots missing _ARCH.md.
    4  Recursive scan found new gaps (not in baseline).
    6  Both strict and recursive failures.
    8  Stub markers in guarded src/services/ _ARCH.md.
    Other bits combine (e.g. 10 = strict + stub).

Run from myrm-agent-frontend root::

    python3 scripts/check_fractal_docs.py
    python3 scripts/check_fractal_docs.py --write-baseline
    python3 scripts/check_fractal_docs.py --strict-roots
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

_DEFAULT_BASELINE = Path(__file__).resolve().parent / "ci" / "fractal_docs_baseline.txt"

_PRUNE_DIR_NAMES: frozenset[str] = frozenset(
    {
        "__tests__",
        "node_modules",
        ".next",
        "dist",
        "build",
        "__pycache__",
    }
)

_RECURSIVE_SCAN_ROOTS: tuple[str, ...] = (
    "src/components/features",
    "src/hooks",
    "src/store",
    "src/lib",
    "src/services",
)

_STRICT_ROOTS: tuple[str, ...] = (
    "src/app",
    "src/components",
    "src/hooks",
    "src/store",
    "src/lib",
    "src/services",
    "src/i18n",
    "src/types",
)

_STUB_MARKERS = ("待补", "（见目录）")
_NO_STUB_PREFIXES = ("src/services/",)


def _is_pruned_dir(path: Path) -> bool:
    if path.name in _PRUNE_DIR_NAMES:
        return True
    if path.name.startswith("[") and path.name.endswith("]"):
        return True
    return "node_modules" in path.parts


def _has_source_file(directory: Path) -> bool:
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix not in {".ts", ".tsx"}:
            continue
        if ".test." in entry.name or ".spec." in entry.name:
            continue
        return True
    return False


def _iter_dirs(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    yield root
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        if _is_pruned_dir(path):
            continue
        yield path


def _rel_frontend(frontend_root: Path, path: Path) -> str:
    return str(path.relative_to(frontend_root)).replace("\\", "/")


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


def _write_baseline(path: Path, entries: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(sorted(entries))
    path.write_text(
        "# src-relative directories grandfathered without _ARCH.md (one per line)\n"
        f"{body}\n",
        encoding="utf-8",
    )


def _missing_strict_roots(frontend_root: Path) -> list[str]:
    missing: list[str] = []
    for rel in _STRICT_ROOTS:
        directory = frontend_root / rel
        if not directory.is_dir():
            continue
        if not (directory / "_ARCH.md").is_file():
            missing.append(rel)

    features_root = frontend_root / "src/components/features"
    if features_root.is_dir():
        for child in sorted(features_root.iterdir()):
            if not child.is_dir() or _is_pruned_dir(child):
                continue
            if not _has_source_file(child):
                continue
            if not (child / "_ARCH.md").is_file():
                missing.append(_rel_frontend(frontend_root, child))
    return missing


def _missing_recursive(frontend_root: Path, baseline: frozenset[str]) -> list[str]:
    missing: list[str] = []
    for rel_root in _RECURSIVE_SCAN_ROOTS:
        scan_root = frontend_root / rel_root
        if not scan_root.is_dir():
            continue
        for directory in _iter_dirs(scan_root):
            if not _has_source_file(directory):
                continue
            rel = _rel_frontend(frontend_root, directory)
            if (directory / "_ARCH.md").is_file():
                continue
            if rel in baseline:
                continue
            missing.append(rel)
    return missing


def _stub_arch_files(frontend_root: Path) -> list[str]:
    bad: list[str] = []
    src_root = frontend_root / "src"
    if not src_root.is_dir():
        return bad
    for arch in sorted(src_root.rglob("_ARCH.md")):
        if any(p in _PRUNE_DIR_NAMES for p in arch.parts):
            continue
        rel = _rel_frontend(frontend_root, arch.parent)
        if not any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in _NO_STUB_PREFIXES):
            continue
        if any(marker in arch.read_text(encoding="utf-8") for marker in _STUB_MARKERS):
            bad.append(_rel_frontend(frontend_root, arch))
    return bad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontend-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_DEFAULT_BASELINE,
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write current recursive gaps to baseline (maintainers only).",
    )
    parser.add_argument(
        "--strict-roots",
        action="store_true",
        help="Only check module roots and features/* top-level folders.",
    )
    parser.add_argument(
        "--no-stub",
        action="store_true",
        help="Fail if src/services/** _ARCH.md contains stub markers.",
    )
    args = parser.parse_args(argv)

    frontend_root: Path = args.frontend_root.resolve()
    baseline_path = args.baseline.resolve()

    if args.write_baseline:
        gaps = _missing_recursive(frontend_root, frozenset())
        _write_baseline(baseline_path, gaps)
        print(f"Wrote {len(gaps)} entries to {baseline_path}")
        return 0

    strict_missing = _missing_strict_roots(frontend_root)
    recursive_missing: list[str] = []
    if not args.strict_roots:
        baseline = _load_baseline(baseline_path)
        recursive_missing = _missing_recursive(frontend_root, baseline)

    stub_bad: list[str] = []
    if args.no_stub:
        stub_bad = _stub_arch_files(frontend_root)

    if strict_missing:
        print("ERROR: Strict roots missing _ARCH.md:", file=sys.stderr)
        for rel in strict_missing:
            print(f"  - {rel}", file=sys.stderr)

    if recursive_missing:
        print("ERROR: Directories missing _ARCH.md (not in baseline):", file=sys.stderr)
        for rel in recursive_missing:
            print(f"  - {rel}", file=sys.stderr)

    if stub_bad:
        print("ERROR: _ARCH.md stub markers in src/services/:", file=sys.stderr)
        for rel in stub_bad:
            print(f"  - {rel}", file=sys.stderr)

    if not strict_missing and not recursive_missing and not stub_bad:
        scope = "strict roots"
        if not args.strict_roots:
            scope += " + recursive (baseline)"
        if args.no_stub:
            scope += " + no stub in services"
        print(f"OK ({scope}).")
        return 0

    code = 0
    if strict_missing:
        code |= 2
    if recursive_missing:
        code |= 4
    if stub_bad:
        code |= 8
    return code


if __name__ == "__main__":
    raise SystemExit(main())
