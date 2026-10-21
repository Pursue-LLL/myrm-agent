#!/usr/bin/env python3
"""Assert git tag version matches pyproject.toml project.version.

[INPUT]
- GITHUB_REF env (refs/tags/harness-vX.Y.Z on tag push)

[OUTPUT]
- main(): exit 0 when tag matches or push is not a harness release tag

[POS]
First gate in the monorepo harness publish workflow, before building and uploading the wheel.
The pipeline is shared with the desktop release, so the harness prefix is what separates them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from harness_packaging.version import read_harness_version  # noqa: E402

_TAG_PREFIX = "refs/tags/harness-v"


def main() -> int:
    ref = os.environ.get("GITHUB_REF", "")
    if not ref.startswith(_TAG_PREFIX):
        print("Not a harness release tag push; skipping tag gate")
        return 0

    tag_version = ref.removeprefix(_TAG_PREFIX)
    pyproject_version = read_harness_version(_REPO_ROOT)
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
