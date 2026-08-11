"""Mechanical SSOT for guardrail bash Chrome E2E marker profile (Epic A).

All five contract surfaces must import from here — never duplicate literals:
  1. test_guardrail_bash_chrome_e2e.py @pytest.mark.chrome_e2e
  2. scripts/dev/test.sh guardrail gate
  3. test_guardrail_bash_smoke_static.py
  4. test_e2e_session_profile.py guardrail tests
  5. CHROME_MCP_E2E.md scenario R (human doc mirrors these values)

SHARED migration: flip this module atomically after solo-window live signoff (§20).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final, Literal, TypedDict

ExecutionMode = Literal["SHARED", "PRIVATE"]
AccessScope = Literal["READ", "NAMESPACE_WRITE", "GLOBAL_WRITE"]
Workload = Literal["STANDARD", "LIVE", "DESKTOP"]


class ChromeE2EMarkerProfile(TypedDict):
    execution_mode: ExecutionMode
    access_scope: AccessScope
    workload: Workload
    private_reason: str


# TAB-9: bash safety interceptor needs process isolation from shared-stack peers —
# a peer's bash sandbox mutation must never interleave with the guardrail verdict.
# Live signoff evidence: 96881/30528 PRIVATE 3/3 GREEN. SHARED flip needs re-signoff (§20).
EXECUTION_MODE: Final[ExecutionMode] = "PRIVATE"
ACCESS_SCOPE: Final[AccessScope] = "NAMESPACE_WRITE"
WORKLOAD: Final[Workload] = "STANDARD"
PRIVATE_REASON: Final[str] = "exclusive_backend"

CHROME_E2E_MARKER_KWARGS: Final[ChromeE2EMarkerProfile] = {
    "execution_mode": EXECUTION_MODE,
    "access_scope": ACCESS_SCOPE,
    "workload": WORKLOAD,
    "private_reason": PRIVATE_REASON,
}

# Grep-compatible literal for test.sh / legacy static checks.
MARKER_EXECUTION_MODE_LITERAL: Final[str] = f'execution_mode="{EXECUTION_MODE}"'

GUARDRAIL_E2E_REL_PATH: Final[str] = (
    "myrm-agent/myrm-agent-server/tests/e2e/test_guardrail_bash_chrome_e2e.py"
)

_FORBIDDEN_LITERAL_MODES: Final[frozenset[str]] = frozenset(
    {f'execution_mode="{mode}"' for mode in ("SHARED", "PRIVATE") if mode != EXECUTION_MODE}
)


def validate_e2e_test_file(path: Path) -> None:
    """Fail closed when pytest marker drifts from mechanical SSOT."""
    text = path.read_text(encoding="utf-8")
    if "guardrail_e2e_ssot" not in text:
        raise RuntimeError(
            "E2E_GUARDRAIL_MARKER_INVALID: test file must import guardrail_e2e_ssot"
        )
    if "CHROME_E2E_MARKER_KWARGS" not in text:
        raise RuntimeError(
            "E2E_GUARDRAIL_MARKER_INVALID: marker must spread CHROME_E2E_MARKER_KWARGS"
        )
    for literal in _FORBIDDEN_LITERAL_MODES:
        if literal in text:
            raise RuntimeError(
                f"E2E_GUARDRAIL_MARKER_INVALID: inline {literal} forbidden — use SSOT module"
            )
    if 'e2e_search_policy("empty")' not in text:
        raise RuntimeError(
            'E2E_GUARDRAIL_MARKER_INVALID: guardrail must declare e2e_search_policy("empty")'
        )
    tree = ast.parse(text, filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name != "test_guardrail_bash_progress_step_and_safety_badge_render":
            continue
        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "chrome_e2e"
            ):
                continue
            spread_ok = False
            if (
                len(decorator.args) == 1
                and isinstance(decorator.args[0], ast.Starred)
                and isinstance(decorator.args[0].value, ast.Name)
                and decorator.args[0].value.id == "CHROME_E2E_MARKER_KWARGS"
            ):
                spread_ok = True
            for keyword in decorator.keywords:
                if (
                    keyword.arg is None
                    and isinstance(keyword.value, ast.Name)
                    and keyword.value.id == "CHROME_E2E_MARKER_KWARGS"
                ):
                    spread_ok = True
                    break
            if spread_ok:
                return
    raise RuntimeError(
        "E2E_GUARDRAIL_MARKER_INVALID: chrome_e2e marker must use **CHROME_E2E_MARKER_KWARGS"
    )
