"""Shell-safe validation for `.env.test` before bash `source`.

[INPUT]
- Path to `.env.test` (KEY=VALUE dotenv file)

[OUTPUT]
- validate_env_test_shell_safe() -> list[str] error messages (empty = OK)

[POS]
PreflightContract S0 — fail loud in <5s when a maintainer adds a stray line (BUG-DG-2026-08-07-001).
"""

from __future__ import annotations

import re
from pathlib import Path

_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def validate_env_test_shell_safe(path: Path) -> list[str]:
    """Return human-readable errors; empty list means safe to ``source`` in bash."""
    if not path.is_file():
        return [f"missing file: {path}"]
    errors: list[str] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if _ASSIGNMENT_RE.match(line):
            continue
        errors.append(
            f"{path.name}:{line_no}: not a comment or KEY=VALUE assignment: {raw!r}"
        )
    return errors


def assert_env_test_shell_safe(path: Path) -> None:
    errors = validate_env_test_shell_safe(path)
    if errors:
        detail = "; ".join(errors[:5])
        if len(errors) > 5:
            detail += f"; … and {len(errors) - 5} more"
        raise RuntimeError(f"ENV_TEST_SHELL_UNSAFE: {detail}")
