#!/usr/bin/env python3
"""Assert the pushed release tag matches pyproject.toml project.version.

[INPUT]
- GITHUB_REF env (refs/tags/harness-vX.Y.Z on tag push)

[OUTPUT]
- main(): exit 0 when tag matches or push is not a harness release tag

[POS]
First gate in the harness PyPI publish workflow, before building and uploading the wheel.
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TAG_PREFIX = "refs/tags/harness-v"


def _read_project_version() -> str:
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        msg = "Missing project.version in pyproject.toml"
        raise ValueError(msg)
    return version


def main() -> int:
    ref = os.environ.get("GITHUB_REF", "")
    if not ref.startswith(_TAG_PREFIX):
        print("Not a harness release tag push; skipping tag gate")
        return 0

    tag_version = ref.removeprefix(_TAG_PREFIX)
    pyproject_version = _read_project_version()
    if tag_version != pyproject_version:
        msg = (
            f"Tag harness-v{tag_version} does not match pyproject.toml version {pyproject_version}. "
            "Bump project.version or retag before publishing."
        )
        print(msg, file=sys.stderr)
        return 1

    print(f"Tag matches pyproject version: {pyproject_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
