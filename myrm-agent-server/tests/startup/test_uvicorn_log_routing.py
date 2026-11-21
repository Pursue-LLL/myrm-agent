"""Every uvicorn launch of the server leaves uvicorn's loggers to the application's root handler.

[INPUT]
- app/startup/uvicorn_runner.py (POS: uvicorn server starter, the default launch mode)
- app/main.py (POS: application entry; its script entry is the desktop sidecar's PyInstaller entry)

[OUTPUT]
- Regression coverage of the logging argument of every ``uvicorn.run`` and ``uvicorn.Config`` call under ``app/`` and
  in ``run.py``

[POS]
Startup tests. uvicorn's default ``log_config`` gives its loggers private handlers and stops them from propagating, so
its lines (the traceback of an unhandled exception, a request line with its query string) skip the redacting root
handler ``configure_logging`` installs. ``log_config=None`` leaves them to the root handler. The calls sit where a test
cannot run them (an entry function and a ``__main__`` block), so the guard reads the source.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_KNOWN_ENTRIES = {"app/startup/uvicorn_runner.py", "app/main.py"}
# ``uvicorn.run`` and ``uvicorn.Config`` (what ``uvicorn.Server`` is built from) both default to uvicorn's own log_config.
_LAUNCHES = {"run", "Config"}


def _is_uvicorn_launch(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _LAUNCHES
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "uvicorn"
    )


def _uvicorn_launch_calls() -> dict[str, list[ast.Call]]:
    """The uvicorn launch calls of the server, by path relative to the server root."""
    found: dict[str, list[ast.Call]] = {}
    for path in [*sorted((_SERVER_ROOT / "app").rglob("*.py")), _SERVER_ROOT / "run.py"]:
        text = path.read_text(encoding="utf-8")
        if "uvicorn" not in text:
            continue
        calls = [node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Call) and _is_uvicorn_launch(node)]
        if calls:
            found[path.relative_to(_SERVER_ROOT).as_posix()] = calls
    return found


def test_the_scan_finds_both_launch_paths() -> None:
    """A guard that finds nothing passes for the wrong reason; the script entry is the desktop sidecar's."""
    assert _KNOWN_ENTRIES <= set(_uvicorn_launch_calls())


def test_every_uvicorn_launch_leaves_logging_to_the_root_handler() -> None:
    offenders = []
    for relative_path, calls in _uvicorn_launch_calls().items():
        for call in calls:
            log_config = {keyword.arg: keyword.value for keyword in call.keywords}.get("log_config")
            if not (isinstance(log_config, ast.Constant) and log_config.value is None):
                offenders.append(f"{relative_path}:{call.lineno}")

    assert not offenders, f"A uvicorn launch without log_config=None bypasses the redacting root handler: {offenders}"
