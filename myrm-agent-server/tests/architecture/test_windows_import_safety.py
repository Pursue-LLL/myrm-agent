"""The Windows sidecar must import: no module may need a POSIX-only name while it loads.

The frozen backend runs on Windows, whose stdlib has no `fcntl` / `resource` / `pty` / ..., no `signal.SIGKILL`
and no `os.killpg`. A module that touches one of them as it loads kills the whole backend before it serves
a request: `signal.SIGKILL` as a default argument did exactly that. Three rules, over the harness and the server:

1. Loading a module must not import a POSIX-only module, nor evaluate a POSIX-only `signal` / `os` name
   (module body, class bodies, decorators, default arguments), unless a platform check or a handler for the
   failure guards it.
2. A POSIX-only signal name is referenced nowhere unguarded, call time included. The one POSIX-only call
   that takes such a name, `os.killpg`, is exempt; everything cross-platform names the force-kill signal
   through `os_compat.SIGKILL`.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_SCANNED_ROOTS = (
    _SERVER_ROOT / "app",
    _SERVER_ROOT.parent / "myrm-agent-harness" / "src" / "myrm_agent_harness",
)

_POSIX_ONLY_MODULES = frozenset(
    {"fcntl", "resource", "pwd", "grp", "termios", "tty", "pty", "syslog", "readline", "curses", "posix", "uvloop"}
)
# Everything else in `signal` is missing on Windows (https://docs.python.org/3/library/signal.html#module-contents).
_WINDOWS_SIGNAL_NAMES = frozenset(
    {"SIGABRT", "SIGFPE", "SIGILL", "SIGINT", "SIGSEGV", "SIGTERM", "SIGBREAK", "SIG_DFL", "SIG_IGN"}
)
_POSIX_ONLY_SIGNAL_FUNCTIONS = frozenset(
    {"alarm", "setitimer", "getitimer", "pause", "pthread_kill", "pthread_sigmask", "sigpending", "sigwait"}
)
_POSIX_ONLY_OS_NAMES = frozenset(
    {
        "fork", "forkpty", "killpg", "getpgid", "getpgrp", "setsid", "setpgid", "setpgrp", "getuid", "geteuid",
        "getgid", "getegid", "setuid", "setgid", "getgroups", "chown", "lchown", "fchown", "chroot", "nice",
        "getloadavg", "mkfifo", "mknod", "uname", "sync", "getpriority", "setpriority", "openpty", "ttyname",
        "ctermid",
    }
)  # fmt: skip
_PLATFORM_NAME = re.compile(r"(?i)^_*(is_?win\w*|win32|windows)$")
_BROAD_HANDLERS = frozenset({"Exception", "BaseException"})
_IMPORT_FAILURES = frozenset({"ImportError", "ModuleNotFoundError"}) | _BROAD_HANDLERS
_ATTRIBUTE_FAILURES = frozenset({"AttributeError"}) | _BROAD_HANDLERS


def _is_posix_only_signal(name: str) -> bool:
    if name.startswith("SIG"):
        return name not in _WINDOWS_SIGNAL_NAMES
    return name in _POSIX_ONLY_SIGNAL_FUNCTIONS or name.startswith("ITIMER_")


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return f"{_dotted(node.func)}()"
    return ""


def _tests_platform(test: ast.expr) -> bool:
    """True when an `if` condition decides by platform or capability: `sys.platform`, `os.name`, `IS_WIN`, `hasattr`."""
    for node in ast.walk(test):
        if isinstance(node, ast.Attribute) and _dotted(node) in {"sys.platform", "os.name", "platform.system"}:
            return True
        if isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if _PLATFORM_NAME.match(name):
                return True
        if isinstance(node, ast.Call) and _dotted(node.func) in {"hasattr", "platform.system"}:
            return True
    return False


def _handled(node: ast.Try | ast.TryStar) -> set[str]:
    names: set[str] = set()
    for handler in node.handlers:
        if handler.type is None:
            names.add("BaseException")
            continue
        for caught in handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]:
            names.add(_dotted(caught).rsplit(".", 1)[-1])
    return names


class _Scan(ast.NodeVisitor):
    """Finds POSIX-only names that the importing interpreter would hit on Windows.

    `load_time_only` follows only what runs while the module loads; otherwise function bodies are scanned too
    (rule 2, signal names only). A finding is `(line, message)`; `_guards` holds the failures the enclosing
    code handles: "import" (ImportError) and "attr" (AttributeError).
    """

    def __init__(self, *, load_time_only: bool) -> None:
        self.findings: list[tuple[int, str]] = []
        self._load_time_only = load_time_only
        self._guards: list[frozenset[str]] = []
        self._signal_aliases = {"signal"}
        self._os_aliases = {"os"}

    def _report(self, node: ast.AST, kind: str, message: str) -> None:
        if not any(kind in guard for guard in self._guards):
            self.findings.append((getattr(node, "lineno", 0), message))

    def _guarded(self, kinds: frozenset[str], *nodes: ast.AST | list[ast.stmt]) -> None:
        self._guards.append(kinds)
        for node in nodes:
            for child in node if isinstance(node, list) else [node]:
                self.visit(child)
        self._guards.pop()

    # --- scopes -----------------------------------------------------------------------------------------
    def _definition(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> None:
        for default in [*node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)]:
            self.visit(default)
        if not isinstance(node, ast.Lambda):
            for decorator in node.decorator_list:
                self.visit(decorator)
        if not self._load_time_only:
            for statement in node.body if isinstance(node.body, list) else [node.body]:
                self.visit(statement)

    visit_FunctionDef = visit_AsyncFunctionDef = visit_Lambda = _definition

    def visit_If(self, node: ast.If) -> None:
        if _dotted(node.test).endswith("TYPE_CHECKING"):
            for statement in node.orelse:
                self.visit(statement)
            return
        self.visit(node.test)
        guard = frozenset({"import", "attr"}) if _tests_platform(node.test) else frozenset()
        self._guarded(guard, node.body, node.orelse)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.visit(node.test)
        guard = frozenset({"import", "attr"}) if _tests_platform(node.test) else frozenset()
        self._guarded(guard, node.body, node.orelse)

    def visit_Try(self, node: ast.Try | ast.TryStar) -> None:
        handled = _handled(node)
        guard = frozenset(
            kind for kind, failures in (("import", _IMPORT_FAILURES), ("attr", _ATTRIBUTE_FAILURES)) if handled & failures
        )
        self._guarded(guard, node.body)
        for part in (*node.handlers, *node.orelse, *node.finalbody):
            self.visit(part)

    visit_TryStar = visit_Try

    def visit_Call(self, node: ast.Call) -> None:
        if _dotted(node.func) in {f"{alias}.killpg" for alias in self._os_aliases}:
            # `os.killpg` exists only on POSIX, so the names it takes are POSIX-only too.
            self.visit(node.func)
            self._guarded(frozenset({"import", "attr"}), *node.args, *(kw.value for kw in node.keywords))
            return
        self.generic_visit(node)

    # --- findings ---------------------------------------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top == "signal" and alias.asname:
                self._signal_aliases.add(alias.asname)
            if top == "os" and alias.asname:
                self._os_aliases.add(alias.asname)
            if self._load_time_only and top in _POSIX_ONLY_MODULES:
                self._report(node, "import", f"import {alias.name}: no such module on Windows")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        top = (node.module or "").split(".")[0]
        if self._load_time_only and top in _POSIX_ONLY_MODULES:
            self._report(node, "import", f"from {node.module} import ...: no such module on Windows")
        for alias in node.names:
            if top == "signal" and _is_posix_only_signal(alias.name):
                self._report(node, "import", f"from signal import {alias.name}: missing on Windows")
            elif self._load_time_only and top == "os" and alias.name in _POSIX_ONLY_OS_NAMES:
                self._report(node, "import", f"from os import {alias.name}: missing on Windows")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        owner = _dotted(node.value)
        if owner in self._signal_aliases and _is_posix_only_signal(node.attr):
            self._report(node, "attr", f"signal.{node.attr}: missing on Windows (use os_compat.SIGKILL to kill)")
        elif self._load_time_only and owner in self._os_aliases and node.attr in _POSIX_ONLY_OS_NAMES:
            self._report(node, "attr", f"os.{node.attr}: missing on Windows")
        self.generic_visit(node)


def _findings(source: str, *, load_time_only: bool) -> list[tuple[int, str]]:
    scan = _Scan(load_time_only=load_time_only)
    scan.visit(ast.parse(source))
    return scan.findings


@functools.cache
def _scan_tree() -> tuple[list[str], list[str]]:
    """`(rule 1, rule 2)` violations over every scanned file; each file is parsed once and its tree dropped."""
    loading: list[str] = []
    signals: list[str] = []
    for root in _SCANNED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for load_time_only, violations in ((True, loading), (False, signals)):
                scan = _Scan(load_time_only=load_time_only)
                scan.visit(tree)
                where = path.relative_to(_SERVER_ROOT.parent)
                violations.extend(f"{where}:{line}  {message}" for line, message in scan.findings)
    return loading, signals


def test_the_scan_covers_the_harness_and_the_server() -> None:
    counts = [sum(1 for _ in root.rglob("*.py")) for root in _SCANNED_ROOTS]
    assert all(count > 300 for count in counts), f"a scanned root is (nearly) empty: {counts}"


def test_loading_a_module_needs_nothing_posix_only() -> None:
    violations, _ = _scan_tree()
    assert not violations, (
        "Importing these modules fails on Windows, which kills the desktop backend at startup. Import the "
        "module inside the function that needs it, wrap it in try/except ImportError, or branch on the "
        "platform:\n" + "\n".join(violations)
    )


def test_no_posix_only_signal_is_named_outside_a_guard() -> None:
    _, violations = _scan_tree()
    assert not violations, (
        "These raise AttributeError on Windows when they run. Name the force-kill signal `os_compat.SIGKILL`:\n"
        + "\n".join(violations)
    )


@pytest.mark.parametrize(
    "source",
    [
        "import signal\ndef kill(pid, sig=signal.SIGKILL): ...",
        "import resource",
        "from fcntl import flock",
        "import signal\nclass Spec:\n    kill = signal.SIGHUP",
        "import signal\n@register(signal.SIGUSR1)\ndef handler(): ...",
        "import os\nPGID = os.getpgid(0)",
        "import os, signal\nos.killpg(1, signal.SIGKILL)",
        "import os\nclass Worker:\n    owner = os.getuid()",
        "from signal import SIGKILL",
        "import signal as sig\nKILL = sig.SIGKILL",
        "if True:\n    import pty",
        "try:\n    import resource\nexcept OSError:\n    pass",
        "import signal\nsignal.alarm(3)",
    ],
)
def test_the_scanner_flags_what_breaks_on_windows(source: str) -> None:
    assert _findings(source, load_time_only=True), source


@pytest.mark.parametrize(
    "source",
    [
        "import sys\nif sys.platform != 'win32':\n    import fcntl",
        "try:\n    import resource\nexcept ImportError:\n    resource = None",
        "try:\n    import pwd\nexcept (ImportError, OSError):\n    pwd = None",
        "import signal, sys\nKILL = signal.SIGTERM if sys.platform == 'win32' else signal.SIGKILL",
        "import signal\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import pty",
        "def spawn():\n    import pty\n    return pty.openpty()",
        "import signal\ndef kill(pid, sig=signal.SIGTERM): ...",
        "import os\nif hasattr(os, 'fork'):\n    PID = os.fork()",
        "import signal\nIS_WIN = False\nif not IS_WIN:\n    signal.signal(signal.SIGALRM, None)",
        "from signal import SIGINT",
        "import os\nPATH = os.getcwd()",
    ],
)
def test_the_scanner_passes_what_windows_can_load(source: str) -> None:
    assert not _findings(source, load_time_only=True), source


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("import signal\ndef kill(proc):\n    proc.send_signal(signal.SIGKILL)", True),
        ("import signal as sig\ndef kill(proc):\n    proc.send_signal(sig.SIGHUP)", True),
        ("import os, signal\ndef kill(pgid):\n    os.killpg(pgid, signal.SIGKILL)", False),
        ("import signal, sys\ndef kill(proc):\n    if sys.platform != 'win32':\n        proc.send_signal(signal.SIGHUP)", False),
        ("import signal\ndef kill(proc):\n    proc.send_signal(signal.SIGTERM)", False),
    ],
)  # fmt: skip
def test_the_scanner_follows_signal_names_into_function_bodies(source: str, flagged: bool) -> None:
    assert bool(_findings(source, load_time_only=False)) is flagged, source
