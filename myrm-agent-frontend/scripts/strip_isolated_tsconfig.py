#!/usr/bin/env python3
"""Strip Next.js isolated-build pollution from tsconfig.json and next-env.d.ts.

When dev runs with MYRM_NEXT_DIST_DIR=.next-isolated-*, Next auto-appends those paths
to tsconfig include and next-env.d.ts imports. CI (check_fractal_docs.py) forbids this.

Run after E2E teardown or ``bun run cleanup``::

    python3 scripts/strip_isolated_tsconfig.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_NEXT_ENV_STANDARD = """/// <reference types="next" />
/// <reference types="next/image-types/global" />
import "./.next/dev/types/routes.d.ts";
import "./.next/dev/types/root-params.d.ts";

// NOTE: This file should not be edited
// see https://nextjs.org/docs/app/api-reference/config/typescript for more information.
"""


def strip_tsconfig(frontend_root: Path) -> list[str]:
    tsconfig_path = frontend_root / "tsconfig.json"
    if not tsconfig_path.is_file():
        return ["tsconfig.json missing"]

    data = json.loads(tsconfig_path.read_text(encoding="utf-8"))
    include = data.get("include", [])
    if not isinstance(include, list):
        return []

    removed: list[str] = []
    cleaned: list[str] = []
    for entry in include:
        if isinstance(entry, str) and ".next-isolated-" in entry:
            removed.append(entry)
            continue
        if isinstance(entry, str):
            cleaned.append(entry)

    if not removed:
        return []

    data["include"] = cleaned
    tsconfig_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return removed


def strip_next_env(frontend_root: Path) -> bool:
    next_env_path = frontend_root / "next-env.d.ts"
    if not next_env_path.is_file():
        return False

    content = next_env_path.read_text(encoding="utf-8")
    if ".next-isolated-" not in content:
        return False

    next_env_path.write_text(_NEXT_ENV_STANDARD, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontend-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    args = parser.parse_args(argv)

    frontend_root: Path = args.frontend_root.resolve()
    removed = strip_tsconfig(frontend_root)
    env_fixed = strip_next_env(frontend_root)

    if removed:
        for entry in removed:
            print(f"Removed tsconfig include: {entry}")
    if env_fixed:
        print("Reset next-env.d.ts to .next/dev/types reference")

    if not removed and not env_fixed:
        print("OK (no isolated tsconfig pollution)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
