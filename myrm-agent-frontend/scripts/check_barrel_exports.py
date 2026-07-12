#!/usr/bin/env python3
"""Fail CI when index.ts barrels appear outside the cross-domain whitelist or allowed prefixes.

Allowed without whitelist entry:
  - src/components/features/**/index.ts
  - src/components/error-boundary/index.ts

Excluded from barrel policy (not re-export barrels):
  - src/i18n/index.ts (Next.js server actions)

Run from myrm-agent-frontend root::

    python3 scripts/check_barrel_exports.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DEFAULT_WHITELIST = Path(__file__).resolve().parent / "ci" / "barrel_whitelist.txt"
_PRUNE = frozenset({"node_modules", ".next", "__tests__", "dist", "build"})
_FEATURE_PREFIX = "src/components/features/"
_ERROR_BOUNDARY = "src/components/error-boundary/index.ts"
_I18N_EXCLUDE = "src/i18n/index.ts"


def _load_whitelist(path: Path) -> frozenset[str]:
    if not path.is_file():
        return frozenset()
    entries: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.add(stripped.replace("\\", "/"))
    return frozenset(entries)


def _iter_index_files(src_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(src_root.rglob("index.ts")):
        if not path.is_file():
            continue
        if any(part in _PRUNE for part in path.parts):
            continue
        files.append(path)
    return files


def _is_allowed(rel_posix: str, whitelist: frozenset[str]) -> bool:
    if rel_posix == _I18N_EXCLUDE:
        return True
    if rel_posix in whitelist:
        return True
    if rel_posix == _ERROR_BOUNDARY:
        return True
    if rel_posix.startswith(_FEATURE_PREFIX):
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "src",
    )
    parser.add_argument("--whitelist", type=Path, default=_DEFAULT_WHITELIST)
    args = parser.parse_args(argv)

    src_root: Path = args.src_root.resolve()
    frontend_root = src_root.parent
    whitelist = _load_whitelist(args.whitelist.resolve())

    violations: list[str] = []
    for index_path in _iter_index_files(src_root):
        rel = index_path.relative_to(frontend_root).as_posix()
        if not _is_allowed(rel, whitelist):
            violations.append(rel)

    if violations:
        print("ERROR: index.ts barrel outside allowed policy:", file=sys.stderr)
        for path in sorted(violations):
            print(f"  - {path}", file=sys.stderr)
        print(
            "Add to scripts/ci/barrel_whitelist.txt (cross-domain only) "
            "or move under src/components/features/.",
            file=sys.stderr,
        )
        return 1

    print(f"OK (barrel policy, {len(whitelist)} cross-domain whitelist entries).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
