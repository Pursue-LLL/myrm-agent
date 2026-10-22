#!/usr/bin/env python3
"""Reject pyright findings for unbound and undefined names.

[INPUT]
- pyright ``--outputjson`` report path (argv[1])

[OUTPUT]
- exit 0 when no ``reportUnboundVariable`` / ``reportUndefinedVariable`` errors exist
- exit 1 with the offending locations otherwise

[POS]
CI gate for the "name used before it exists" bug class (the memo turn-identity regression).
Runs on the whole server project; other pyright rules are intentionally ignored because the
repository still carries a large pre-existing baseline for them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BLOCKING_RULES = frozenset({"reportUnboundVariable", "reportUndefinedVariable"})


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_pyright_unbound.py <pyright-output.json>", file=sys.stderr)
        return 2
    report = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    findings = [
        diagnostic
        for diagnostic in report.get("generalDiagnostics", [])
        if diagnostic.get("severity") == "error" and diagnostic.get("rule") in _BLOCKING_RULES
    ]
    if not findings:
        print("pyright: no unbound or undefined names")
        return 0
    print(f"pyright: {len(findings)} unbound/undefined name error(s)", file=sys.stderr)
    for diagnostic in findings[:50]:
        start = diagnostic.get("range", {}).get("start", {})
        line = int(start.get("line", 0)) + 1
        print(f"  {diagnostic.get('file')}:{line} [{diagnostic.get('rule')}] {diagnostic.get('message')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
