"""Reads a pytest command line: whether it selects a live chrome_e2e test and how its timeout arguments are applied."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from dev_gate.contract.wall_clock import resolve_e2e_wall_profile


def _normalize_pytest_timeout_value(raw: str, *, floor: int, ceiling: bool) -> str:
    if not raw.isdigit():
        return raw
    value = int(raw)
    if ceiling:
        return str(min(value, floor))
    if value < floor:
        return str(floor)
    return raw


_CHROME_E2E_PYTEST_FILE = re.compile(r"(^|[/\\])test_[^/\\]*_chrome_e2e\.py(::|$)")
_SERVER_E2E_ROOT = Path(__file__).resolve().parents[5] / "myrm-agent-server"


def _resolve_chrome_e2e_test_path(path_arg: str) -> Path | None:
    file_part = path_arg.split("::", 1)[0]
    prefixes = (
        "myrm-agent/myrm-agent-server/",
        "myrm-agent-server/",
    )
    rel = file_part
    for prefix in prefixes:
        if rel.startswith(prefix):
            rel = rel.removeprefix(prefix)
            break
    candidate = _SERVER_E2E_ROOT / rel
    if candidate.is_file():
        return candidate
    return None


def explicit_node_has_chrome_e2e_marker(path_arg: str) -> bool:
    """True when path_arg selects a test function decorated with pytest.mark.chrome_e2e."""
    if "::" not in path_arg:
        return True
    file_path = _resolve_chrome_e2e_test_path(path_arg)
    if file_path is None:
        return True
    test_name = path_arg.split("::", 1)[1]
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name != test_name:
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "chrome_e2e"
            ):
                return True
        return False
    return False


def pytest_argv_needs_live_chrome_e2e(
    argv: tuple[str, ...],
    *,
    run_e2e_tests: bool = False,
) -> bool:
    """True when ./myrm-dev test argv selects formal chrome_e2e (marker or *_chrome_e2e.py).

    Must not match unit-test node ids or -k filters that merely contain the substring
    ``chrome_e2e`` (gate tests live under scripts/dev/tests).

    Explicit ``*_chrome_e2e.py::test_name`` node ids without ``@pytest.mark.chrome_e2e``
    (integration-only signoff legs) do not require live Chrome attach / ADMIT.
    """
    next_is_marker = False
    chrome_paths: list[str] = []
    for arg in argv:
        if next_is_marker:
            next_is_marker = False
            if "chrome_e2e" in arg:
                return True
            continue
        if arg in {"-m", "--markers"}:
            next_is_marker = True
            continue
        if arg.startswith("-"):
            continue
        if _CHROME_E2E_PYTEST_FILE.search(arg):
            chrome_paths.append(arg)
    if chrome_paths:
        return any(
            explicit_node_has_chrome_e2e_marker(path_arg) for path_arg in chrome_paths
        )
    if run_e2e_tests:
        return any(_CHROME_E2E_PYTEST_FILE.search(arg) for arg in argv)
    return False


def apply_chrome_e2e_pytest_timeout_args(
    floor: int,
    args: tuple[str, ...],
) -> tuple[str, ...]:
    """Ensure pytest CLI --timeout respects dev floor or signoff ceiling."""
    ceiling_mode = resolve_e2e_wall_profile() == "signoff"
    out: list[str] = []
    found = False
    next_is_timeout = False
    for arg in args:
        if next_is_timeout:
            next_is_timeout = False
            out.append(
                _normalize_pytest_timeout_value(arg, floor=floor, ceiling=ceiling_mode)
            )
            found = True
            continue
        if arg.startswith("--timeout="):
            value = arg.split("=", 1)[1]
            normalized = _normalize_pytest_timeout_value(
                value, floor=floor, ceiling=ceiling_mode
            )
            out.append(f"--timeout={normalized}")
            found = True
        elif arg == "--timeout":
            next_is_timeout = True
            out.append(arg)
        else:
            out.append(arg)
    if not found:
        out.append(f"--timeout={floor}")
    return tuple(out)
