"""Every Myrm-owned path derives from the state root, never from the user's home directory.

[INPUT]
- app/**/*.py and myrm-agent-harness/src/**/*.py: every home-derived expression (``Path.home()``, a ``"~/..."`` literal,
  ``HOME``) that shares a function (or top-level statement) with a Myrm-owned directory name (``.myrm``, ``myrm-agent``, ...)

[OUTPUT]
- Fails when code builds ``~/.myrm/...`` by hand: such a path ignores ``MYRM_DATA_DIR``, so an isolated runtime (a test run,
  a second profile) reads and writes the real user's data, and the real user's data leaks into that run.

[POS]
tests/architecture/test_state_paths_follow_data_dir.py - guard for ``myrm_agent_harness.infra.data_dir``: the state root
resolver is the only place that turns the default directory name into a path. Reading another tool's directory
(``~/.claude``, ``~/.ssh``) names no Myrm directory and is not affected.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

_APP = Path(__file__).resolve().parents[2] / "app"
_HARNESS = Path(__file__).resolve().parents[3] / "myrm-agent-harness" / "src" / "myrm_agent_harness"

# A path component naming a Myrm-owned directory: ".myrm", ".myrm-agent", "myrm", "myrm-agent-harness".
_MYRM_DIR_NAME = re.compile(r"(^|[/\\])\.?myrm(?![A-Za-z0-9])")
_HOME_ENV_NAMES = frozenset({"HOME", "USERPROFILE"})
_HOME_MARKERS = ("home(", "~", "HOME", "USERPROFILE")

# Files that may name a Myrm directory next to a home-derived expression, each with the reason it is safe.
_ALLOWED: dict[str, str] = {
    "myrm_agent_harness/toolkits/acp/toolchains/manager.py": (
        "version-keyed third-party CLI installs (node-<version>, an npm prefix) shared by every Myrm process on the "
        "machine like a package-manager cache; the install endpoint is the only writer and no test calls it"
    ),
    "app/config/settings.py": (
        "the settings field that reads MYRM_DATA_DIR through its alias: the literal is its documented default, "
        "pinned by test_data_dir_contract"
    ),
    "myrm_agent_harness/agent/creator_mode/roaming_gateway.py": (
        "canonical path labels recorded in sync records (one is a cloud:// URL); the gateway never opens them as files"
    ),
    "app/server/stack_epoch.py": (
        "developer supervisor state under the login home (~/.local/state/myrm-dev), not product data; "
        "it is deliberately read from the real user home"
    ),
}


def _is_home_derived(node: ast.AST) -> bool:
    """``Path.home()``, a ``"~..."`` literal (expanded elsewhere) or the name of a home environment variable.

    ``expanduser()`` on a caller-supplied path is not listed: the caller chose that path, the code did not.
    """
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and (node.value in _HOME_ENV_NAMES or node.value.startswith("~"))
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "home":
        return False
    owner = node.func.value
    return (isinstance(owner, ast.Name) and owner.id == "Path") or (isinstance(owner, ast.Attribute) and owner.attr == "Path")


def _docstring_ids(tree: ast.Module) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def home_derived_myrm_paths(source: str) -> Iterator[tuple[int, str]]:
    """``(line, name)`` for each home-derived expression sharing a scope with a Myrm-owned directory name.

    A scope is the innermost function, or the top-level statement when the code sits outside any function.
    """
    if not any(marker in source for marker in _HOME_MARKERS):
        return
    tree = ast.parse(source)
    skipped = _docstring_ids(tree)
    scopes: dict[int, tuple[list[int], list[str]]] = {}

    def collect(node: ast.AST, scope: int) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            scope = id(node)
        homes, names = scopes.setdefault(scope, ([], []))
        if _is_home_derived(node):
            homes.append(getattr(node, "lineno", 0))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skipped:
            if _MYRM_DIR_NAME.search(node.value):
                names.append(node.value)
        for child in ast.iter_child_nodes(node):
            collect(child, scope)

    for statement in tree.body:
        collect(statement, id(statement))

    for homes, names in scopes.values():
        if homes and names:
            yield from ((line, names[0]) for line in sorted(set(homes)))


def _offenders() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for root, prefix in ((_APP, "app"), (_HARNESS, "myrm_agent_harness")):
        for path in sorted(root.rglob("*.py")):
            relative = f"{prefix}/{path.relative_to(root).as_posix()}"
            hits = [f"{relative}:{line}: {name!r}" for line, name in home_derived_myrm_paths(path.read_text(encoding="utf-8"))]
            if hits:
                found[relative] = hits
    return found


def test_the_harness_sources_are_where_the_scan_expects_them() -> None:
    assert _HARNESS.is_dir(), f"harness sources not found at {_HARNESS}: the scan would silently check nothing"


def test_no_module_builds_a_myrm_path_from_the_home_directory() -> None:
    offenders = [hit for relative, hits in _offenders().items() if relative not in _ALLOWED for hit in hits]

    assert not offenders, (
        "derive Myrm-owned paths from myrm_agent_harness.infra.data_dir.resolve_data_dir() so MYRM_DATA_DIR relocates them; "
        "a path built from the home directory is shared with the real user's data:\n" + "\n".join(offenders)
    )


def test_every_allowed_file_still_needs_its_exemption() -> None:
    found = _offenders()
    stale = sorted(path for path in _ALLOWED if path not in found)

    assert not stale, f"no longer builds a Myrm path from the home directory, drop it from _ALLOWED: {stale}"


class TestTheScannerSeesWhatItShould:
    def test_a_path_built_from_the_home_directory_is_found(self) -> None:
        source = 'def f():\n    return Path.home() / ".myrm" / "cache"\n'

        assert list(home_derived_myrm_paths(source)) == [(2, ".myrm")]

    def test_a_home_taken_in_one_step_and_joined_in_the_next_is_found(self) -> None:
        source = 'def f():\n    home = Path.home()\n    return home / ".myrm" / "cache"\n'

        assert list(home_derived_myrm_paths(source)) == [(2, ".myrm")]

    def test_a_tilde_string_expanded_in_place_is_found(self) -> None:
        source = 'ROOT = Path("~/.myrm/skills").expanduser()\n'

        assert list(home_derived_myrm_paths(source)) == [(1, "~/.myrm/skills")]

    def test_a_tilde_default_argument_is_found(self) -> None:
        source = 'def store(data, *, blob_dir="~/.myrm/blobs"):\n    return Path(blob_dir).expanduser()\n'

        assert list(home_derived_myrm_paths(source)) == [(1, "~/.myrm/blobs")]

    def test_a_tilde_class_attribute_is_found(self) -> None:
        source = 'class Config:\n    blob_path: str = "~/.myrm/blobs"\n'

        assert list(home_derived_myrm_paths(source)) == [(2, "~/.myrm/blobs")]

    def test_expanding_a_caller_supplied_path_next_to_a_workspace_local_name_is_not_a_finding(self) -> None:
        source = 'def db(root):\n    return Path(root).expanduser() / ".myrm" / "events.db"\n'

        assert list(home_derived_myrm_paths(source)) == []

    def test_a_cache_directory_named_after_myrm_is_found(self) -> None:
        source = 'def f():\n    return Path.home() / ".cache" / "myrm"\n'

        assert list(home_derived_myrm_paths(source)) == [(2, "myrm")]

    def test_a_home_variable_from_the_environment_is_found(self) -> None:
        source = 'def f():\n    return os.environ["HOME"] + "/.myrm-agent"\n'

        assert list(home_derived_myrm_paths(source)) == [(2, "/.myrm-agent")]

    def test_a_module_level_constant_is_found(self) -> None:
        source = 'CACHE = Path.home() / ".myrm" / "cache"\n'

        assert list(home_derived_myrm_paths(source)) == [(1, ".myrm")]

    def test_reading_another_tools_directory_is_not_a_finding(self) -> None:
        source = 'def f():\n    return Path.home() / ".claude" / "projects"\n'

        assert list(home_derived_myrm_paths(source)) == []

    def test_the_state_root_resolver_is_not_a_finding(self) -> None:
        source = 'def f():\n    return resolve_data_dir() / "cache"\n'

        assert list(home_derived_myrm_paths(source)) == []

    def test_a_home_and_a_myrm_name_in_different_functions_are_not_a_finding(self) -> None:
        source = 'def a():\n    return Path.home() / ".ssh"\n\ndef b():\n    return base / ".myrm"\n'

        assert list(home_derived_myrm_paths(source)) == []

    def test_a_docstring_that_mentions_the_default_directory_is_not_a_finding(self) -> None:
        source = 'def f():\n    """Defaults to ~/.myrm."""\n    return Path.home()\n'

        assert list(home_derived_myrm_paths(source)) == []

    def test_an_uppercase_environment_variable_name_is_not_a_myrm_directory(self) -> None:
        source = 'def f():\n    return Path(os.environ.get("MYRM_DATA_DIR", "")).expanduser()\n'

        assert list(home_derived_myrm_paths(source)) == []
