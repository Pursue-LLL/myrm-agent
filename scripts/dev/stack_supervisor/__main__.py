"""CLI entry: python -m stack_supervisor <cmd>."""

from __future__ import annotations

import sys

from stack_supervisor.client import main

if __name__ == "__main__":
    raise SystemExit(main())
