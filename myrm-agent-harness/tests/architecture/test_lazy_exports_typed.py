"""Architecture guard: a lazily exported name is visible to type checkers as what it really is.

A package whose ``__init__`` resolves its public names in a module-level ``__getattr__`` hides them from type
checkers: ``from pkg import name`` is typed ``object`` (not callable, no attributes) unless the name is also bound
statically. The packages mirror their exports in an ``if TYPE_CHECKING:`` block; the block has to stay one-to-one
with ``__all__`` and with the table the runtime resolves from, or the types lie.
"""

from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_HARNESS_SRC = _REPO_ROOT / "src" / "myrm_agent_harness"
_TABLE_NAMES = ("_EXPORTS", "_LAZY_IMPORTS")

# ``api`` mirrors its ~300 names in ``api/__init__.pyi`` (checked by tests/api/test_public_surface.py); a second
# mirror inside ``__init__.py`` would only duplicate it.
_MIRRORED_BY_STUB = frozenset({"api/__init__.py"})
# Names a package's ``__getattr__`` builds on first access: no importable definition exists to mirror.
_BUILT_IN_GETATTR = {
    "toolkits/retriever/__init__.py": frozenset({"preload_retriever_models", "start_background_preload"}),
}


@dataclass(frozen=True, slots=True)
class _Lazy:
    """What a package's ``__init__`` declares: its names, what is bound statically, and the runtime table."""

    all_names: tuple[str, ...] | None
    bound: dict[str, tuple[str, str] | None]  # name -> (module, attr) for an import, None for a definition
    table: dict[str, tuple[str, str]]


def _dotted_package(rel: str) -> str:
    return ".".join(("myrm_agent_harness", *Path(rel).parent.parts))


def _resolve(module: str, package: str) -> str:
    """The absolute module of a table or import target; a leading dot is relative to ``package``."""
    if not module.startswith("."):
        return module
    dots = len(module) - len(module.lstrip("."))
    base = package.split(".")
    if dots > 1:
        base = base[: -(dots - 1)]
    return ".".join([*base, module.lstrip(".")]).rstrip(".")


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _bind(nodes: list[ast.stmt], package: str, bound: dict[str, tuple[str, str] | None]) -> None:
    for node in nodes:
        if isinstance(node, ast.ImportFrom):
            module = _resolve("." * node.level + (node.module or ""), package)
            for alias in node.names:
                bound[alias.asname or alias.name] = (module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound[(alias.asname or alias.name).split(".")[0]] = None
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            bound[node.name] = None
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(target, ast.Name):
                    bound[target.id] = None
        elif isinstance(node, ast.If):
            _bind(node.body, package, bound)
            _bind(node.orelse, package, bound)


def _assigned(tree: ast.Module, name: str) -> ast.expr | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node.value
    return None


def _literal_table(value: ast.expr, constants: dict[str, str]) -> dict[str, tuple[str, str]]:
    """A ``{name: (module, attr)}`` literal; a module may be a module-level string constant (``_CR = "..."``)."""

    def text(node: ast.expr) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name) and node.id in constants:
            return constants[node.id]
        raise AssertionError(f"lazy table entry is not a literal: {ast.dump(node)}")

    assert isinstance(value, ast.Dict)
    table: dict[str, tuple[str, str]] = {}
    for key, entry in zip(value.keys, value.values, strict=True):
        assert key is not None and isinstance(entry, ast.Tuple) and len(entry.elts) == 2
        table[text(key)] = (text(entry.elts[0]), text(entry.elts[1]))
    return table


def _scan(source: str, package: str) -> _Lazy | None:
    """The lazy declarations of ``source``, or None when it has no module-level ``__getattr__``."""
    tree = ast.parse(source)
    if not any(isinstance(n, ast.FunctionDef) and n.name == "__getattr__" for n in tree.body):
        return None
    bound: dict[str, tuple[str, str] | None] = {}
    _bind(tree.body, package, bound)

    declared = _assigned(tree, "__all__")
    all_names: tuple[str, ...] | None = None
    if isinstance(declared, ast.List | ast.Tuple) and all(
        isinstance(e, ast.Constant) and isinstance(e.value, str) for e in declared.elts
    ):
        all_names = tuple(str(e.value) for e in declared.elts if isinstance(e, ast.Constant))

    constants = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    table: dict[str, tuple[str, str]] = {}
    for table_name in _TABLE_NAMES:
        value = _assigned(tree, table_name)
        if value is not None:
            table = {
                name: (_resolve(module, package), attr)
                for name, (module, attr) in _literal_table(value, constants).items()
            }
    return _Lazy(all_names, bound, table)


def _problems(lazy: _Lazy, *, built_in_getattr: frozenset[str] = frozenset()) -> list[str]:
    if lazy.all_names is None:
        return ["__all__ is not a literal list of strings, so the exported names cannot be checked"]
    found = [
        f"{name} is exported but not bound for type checkers"
        for name in lazy.all_names
        if name not in lazy.bound and name not in built_in_getattr
    ]
    for name, target in lazy.table.items():
        if name not in lazy.all_names:
            found.append(f"{name} is in the lazy table but not in __all__")
        elif name in lazy.bound and lazy.bound[name] != target:
            found.append(f"{name}: the lazy table resolves {target}, the TYPE_CHECKING import says {lazy.bound[name]}")
    return found


def _all_lazy_packages() -> dict[str, _Lazy]:
    packages: dict[str, _Lazy] = {}
    for init in sorted(_HARNESS_SRC.rglob("__init__.py")):
        rel = init.relative_to(_HARNESS_SRC).as_posix()
        lazy = _scan(init.read_text(encoding="utf-8"), _dotted_package(rel))
        if lazy is not None:
            packages[rel] = lazy
    return packages


def _lazy_packages() -> dict[str, _Lazy]:
    return {rel: lazy for rel, lazy in _all_lazy_packages().items() if rel not in _MIRRORED_BY_STUB}


@pytest.mark.architecture
def test_every_lazily_exported_name_is_typed() -> None:
    packages = _lazy_packages()
    assert len(packages) >= 20, "the scan stopped finding the lazy packages"

    violations = [
        f"{rel}: {problem}"
        for rel, lazy in packages.items()
        for problem in _problems(lazy, built_in_getattr=_BUILT_IN_GETATTR.get(rel, frozenset()))
    ]
    assert not violations, "\n".join(violations)


@pytest.mark.architecture
def test_every_lazily_exported_name_resolves() -> None:
    """A name ``__all__`` promises but its module does not define fails on first use, not when the package imports."""
    unresolved: list[str] = []
    for rel in _all_lazy_packages():
        module = importlib.import_module(_dotted_package(rel))
        for name in module.__all__:
            try:
                getattr(module, name)
            except (AttributeError, ImportError) as error:
                unresolved.append(f"{rel}: {name} ({type(error).__name__}: {error})")
    assert not unresolved, "\n".join(unresolved)


def test_the_exemptions_are_still_needed() -> None:
    """An exemption that no longer applies is removed, so it cannot hide a later regression."""
    packages = _lazy_packages()
    for rel, names in _BUILT_IN_GETATTR.items():
        lazy = packages[rel]
        assert all(name in (lazy.all_names or ()) and name not in lazy.bound for name in names), rel
    for rel in _MIRRORED_BY_STUB:
        assert (_HARNESS_SRC / rel).with_suffix(".pyi").is_file(), rel


_PACKAGE = "myrm_agent_harness.sample"
_GETATTR = "\n\ndef __getattr__(name: str) -> object:\n    raise AttributeError(name)\n"


def _checked(source: str) -> list[str]:
    lazy = _scan(source, _PACKAGE)
    assert lazy is not None
    return _problems(lazy)


def test_a_package_without_getattr_is_not_a_lazy_package() -> None:
    assert _scan("__all__ = ['a']\n", _PACKAGE) is None


def test_a_mirrored_table_passes() -> None:
    source = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from .types import Thing\n    from myrm_agent_harness.other import tool\n"
        "_EXPORTS = {'Thing': ('.types', 'Thing'), 'tool': ('myrm_agent_harness.other', 'tool')}\n"
        "__all__ = ['Thing', 'tool']\n" + _GETATTR
    )

    assert _checked(source) == []


def test_a_name_without_a_static_binding_is_flagged() -> None:
    source = "_EXPORTS = {'Thing': ('.types', 'Thing')}\n__all__ = ['Thing']\n" + _GETATTR

    assert _checked(source) == ["Thing is exported but not bound for type checkers"]


def test_a_mirror_that_disagrees_with_the_table_is_flagged() -> None:
    source = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from .stale import Thing\n"
        "_EXPORTS = {'Thing': ('.types', 'Thing')}\n__all__ = ['Thing']\n" + _GETATTR
    )

    assert _checked(source) == [
        "Thing: the lazy table resolves ('myrm_agent_harness.sample.types', 'Thing'), "
        "the TYPE_CHECKING import says ('myrm_agent_harness.sample.stale', 'Thing')"
    ]


def test_a_table_name_missing_from_all_is_flagged() -> None:
    source = (
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .types import Thing\n"
        "_EXPORTS = {'Thing': ('.types', 'Thing')}\n__all__ = []\n" + _GETATTR
    )

    assert _checked(source) == ["Thing is in the lazy table but not in __all__"]


def test_a_derived_all_is_flagged() -> None:
    source = "_EXPORTS = {'Thing': ('.types', 'Thing')}\n__all__ = list(_EXPORTS)\n" + _GETATTR

    assert _checked(source) == ["__all__ is not a literal list of strings, so the exported names cannot be checked"]


def test_a_module_constant_in_the_table_is_followed() -> None:
    source = (
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .types import Thing\n"
        "_T = 'myrm_agent_harness.sample.types'\n"
        "_LAZY_IMPORTS = {'Thing': (_T, 'Thing')}\n__all__ = ['Thing']\n" + _GETATTR
    )

    assert _checked(source) == []


def test_relative_targets_resolve_against_the_package() -> None:
    assert _resolve(".types", "pkg.sub") == "pkg.sub.types"
    assert _resolve("..types", "pkg.sub") == "pkg.types"
    assert _resolve("other.mod", "pkg.sub") == "other.mod"
