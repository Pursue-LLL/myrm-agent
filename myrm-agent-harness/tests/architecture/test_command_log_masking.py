"""Architecture guard: a harness log line never quotes a shell command unmasked.

A command carries credentials (``--key x``, ``user:pw@host``) and a log line outlives the call, so every logger call that
interpolates a command variable goes through ``command_preview`` or ``redact_command_line``. A variable is a command
when ``command`` or ``cmd`` is one of the words of its name (``new_command``, ``cmd_str``, ``full_cmd_array``) and no
word says it is something else (``command_type``, ``command_pattern``). The scan is a name tripwire, not a proof: a
command held in a variable named otherwise is not seen.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

_HARNESS_SRC = Path(__file__).resolve().parents[2] / "src" / "myrm_agent_harness"

_LOG_LEVELS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical"})
_LOGGER_NAMES = frozenset({"logger", "_logger", "log", "_log", "logging"})
_MASKING_CALLS = frozenset({"command_preview", "redact_command_line"})
_COMMAND_WORD_RE = re.compile(r"(?:^|_)(?:command|cmd)(?:_|$)")
_OTHER_THING_RE = re.compile(r"(?:^|_)(?:type|name|id|count|index|pattern|result|status|handler|registry)(?:_|$)")

# ``path::function::variable`` entries that are not a command a user or a model wrote.
_ALLOWED = {
    "toolkits/code_execution/sandbox_snapshot.py::_run_quick_command::cmd": "argv of fixed environment probes (git, runtime versions)",
    "agent/meta_tools/file_ops/validators/auto_verify.py::_check_linter_available::detect_cmd": "detection command from the built-in linter table",
    "agent/_internals/agent_runtime.py::run_agent_loop::resume_command": "the graph's resume Command object, not shell text",
}


def _is_command_name(name: str) -> bool:
    return bool(_COMMAND_WORD_RE.search(name)) and not _OTHER_THING_RE.search(name)


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


def _is_log_call(node: ast.Call) -> bool:
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in _LOG_LEVELS):
        return False
    owner = func.value
    owner_name = owner.id if isinstance(owner, ast.Name) else owner.attr if isinstance(owner, ast.Attribute) else ""
    return owner_name in _LOGGER_NAMES


def _unmasked_names(node: ast.AST) -> Iterator[str]:
    """Command-named variables under *node* that no masking call wraps and no ``[0]`` reduces to a program name."""
    if isinstance(node, ast.Call) and _call_name(node) in _MASKING_CALLS:
        return
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and node.slice.value == 0:
        return
    if isinstance(node, ast.Name) and _is_command_name(node.id):
        yield node.id
    elif isinstance(node, ast.Attribute) and _is_command_name(node.attr):
        yield node.attr
    for child in ast.iter_child_nodes(node):
        yield from _unmasked_names(child)


class _LogScanner(ast.NodeVisitor):
    """Collects ``(line, enclosing function, variable)`` for every logger call that quotes a command unmasked."""

    def __init__(self) -> None:
        self.hits: list[tuple[int, str, str]] = []
        self._functions: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter(node)

    def _enter(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._functions.append(node.name)
        self.generic_visit(node)
        self._functions.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if _is_log_call(node):
            arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
            function = self._functions[-1] if self._functions else "<module>"
            for name in sorted({found for argument in arguments for found in _unmasked_names(argument)}):
                self.hits.append((node.lineno, function, name))
        self.generic_visit(node)


def _find_unmasked_command_logs(source: str) -> list[tuple[int, str, str]]:
    scanner = _LogScanner()
    scanner.visit(ast.parse(source))
    return scanner.hits


def _scan_harness() -> dict[str, list[tuple[int, str, str]]]:
    found: dict[str, list[tuple[int, str, str]]] = {}
    for py_file in sorted(_HARNESS_SRC.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        if "command" not in source and "cmd" not in source:
            continue
        hits = _find_unmasked_command_logs(source)
        if hits:
            found[py_file.relative_to(_HARNESS_SRC).as_posix()] = hits
    return found


_RAW_SAMPLES = {
    "f-string": 'def run(command):\n    logger.info(f"running {command}")\n',
    "percent argument": 'def run(command):\n    logger.warning("failed: %s", command)\n',
    "attribute": 'def run(job):\n    logger.error("failed: %s", job.command)\n',
    "joined argv": 'def run(cmd):\n    log.debug("argv %s", " ".join(cmd))\n',
    "method logger": 'class Runner:\n    def run(self, shell_command):\n        self._logger.info("x %s", shell_command)\n',
    "keyword argument": 'def run(command):\n    logger.info("started", extra={"line": command})\n',
    "rewritten command": 'def run(new_command):\n    logger.warning(f"rewrote: {new_command}")\n',
    "argv array": "def run(full_cmd_array):\n    logger.info(f\"spawn {' '.join(full_cmd_array)}\")\n",
}
_MASKED_SAMPLES = {
    "preview": 'def run(command):\n    logger.info("running %s", command_preview(command, 100))\n',
    "redacted": 'def run(command):\n    logger.info(f"running {redact_command_line(command)}")\n',
    "program name": 'def run(cmd):\n    logger.error("%s failed", cmd[0])\n',
    "not a log call": "def run(command):\n    print(command)\n",
    "type of a command": 'def run(command_type):\n    logger.info("type %s", command_type)\n',
    "pattern of a command": 'def run(command_pattern):\n    logger.info("allowed %s", command_pattern)\n',
}


@pytest.mark.architecture
@pytest.mark.parametrize("source", _RAW_SAMPLES.values(), ids=_RAW_SAMPLES.keys())
def test_scanner_flags_a_raw_command(source: str) -> None:
    assert _find_unmasked_command_logs(source)


@pytest.mark.architecture
@pytest.mark.parametrize("source", _MASKED_SAMPLES.values(), ids=_MASKED_SAMPLES.keys())
def test_scanner_passes_a_masked_command(source: str) -> None:
    assert _find_unmasked_command_logs(source) == []


@pytest.mark.architecture
def test_scanner_names_the_enclosing_function() -> None:
    source = 'def outer():\n    def inner(command):\n        logger.info("x %s", command)\n'
    assert _find_unmasked_command_logs(source) == [(3, "inner", "command")]


@pytest.mark.architecture
def test_harness_logs_no_unmasked_command() -> None:
    offenders = [
        f"{relative}:{lineno} {function}() logs `{name}` unmasked"
        for relative, hits in _scan_harness().items()
        for lineno, function, name in hits
        if f"{relative}::{function}::{name}" not in _ALLOWED
    ]
    assert not offenders, (
        "A log line quotes a command unmasked; wrap it in command_preview(command, limit) from "
        "myrm_agent_harness.core.security.redact:\n" + "\n".join(offenders)
    )


@pytest.mark.architecture
def test_every_allowlist_entry_is_still_hit() -> None:
    hit = {
        f"{relative}::{function}::{name}" for relative, hits in _scan_harness().items() for _, function, name in hits
    }
    assert set(_ALLOWED) <= hit, f"stale allowlist entries: {sorted(set(_ALLOWED) - hit)}"
