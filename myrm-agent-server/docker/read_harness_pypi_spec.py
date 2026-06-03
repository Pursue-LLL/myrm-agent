#!/usr/bin/env python3
"""Print the pinned myrm-agent-harness pip install spec from pyproject.toml.

[INPUT]
- myrm-agent-server/pyproject.toml (POS: Server dependency manifest)

[OUTPUT]
- stdout: full pip install spec string (e.g. myrm-agent-harness[...,compiled-core]==0.1.0rc1)

[POS]
Shared harness PyPI pin parser for Docker builder and server install scripts.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'"(myrm-agent-harness\[[^\]]+\]==[0-9a-zA-Z.]+)"', text)
    if match is None:
        print("Could not parse myrm-agent-harness pin from pyproject.toml", file=sys.stderr)
        return 1
    print(match.group(1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
