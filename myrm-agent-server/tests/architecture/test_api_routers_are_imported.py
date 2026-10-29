"""Every module under app/api that defines a module-level APIRouter is imported by another app module.

[POS]
tests/architecture/test_api_routers_are_imported.py

[INPUT]
- app/**/*.py: parsed with ast, never imported

[OUTPUT]
- Fails when a router module has no importer: nothing can mount it, so every route in it answers 404.
  The frontend path gate only notices when a client spells the path out; this one does not depend on a caller.
- Fails when the scan finds no router module at all, so a moved scan root cannot pass silently

A router that is imported but never passed to include_router is out of reach of this check; the frontend path gate
(test_frontend_api_client_paths.py) and the route table (test_api_route_consumers.py) cover the routes a client calls.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

_APP_ROOT = Path(__file__).resolve().parents[2] / "app"
_API_ROOT = _APP_ROOT / "api"


def _module_name(path: Path) -> str:
    parts = path.relative_to(_APP_ROOT.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _defines_router(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
            callee = node.value.func
            if getattr(callee, "id", getattr(callee, "attr", None)) == "APIRouter":
                return True
    return False


def _imported_modules(tree: ast.Module, package: str) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                base = ".".join([*anchor, base] if base else anchor)
            imported.add(base)
            imported.update(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "import_module":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                imported.add(node.args[0].value)
    return imported


def _routers_without_importer() -> list[str]:
    sources = {path: path.read_text(encoding="utf-8") for path in _APP_ROOT.rglob("*.py")}
    router_modules: dict[str, Path] = {}
    for path, text in sources.items():
        if path.is_relative_to(_API_ROOT) and "APIRouter" in text:
            if _defines_router(ast.parse(text, filename=str(path))):
                router_modules[_module_name(path)] = path
    if not router_modules:
        raise AssertionError(f"no module under {_API_ROOT} defines an APIRouter: the scan root or the detection is broken")
    # Every import form spells the last segment of the module it names, so parsing is limited to files that do.
    leaf_names = {module.rpartition(".")[2] for module in router_modules}
    importers: defaultdict[str, set[str]] = defaultdict(set)
    for path, text in sources.items():
        if not any(leaf in text for leaf in leaf_names):
            continue
        module = _module_name(path)
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        for name in _imported_modules(ast.parse(text, filename=str(path)), package):
            importers[name].add(module)
    return sorted(
        path.relative_to(_APP_ROOT.parent).as_posix()
        for module, path in router_modules.items()
        if not importers[module] - {module}
    )


@pytest.mark.architecture
def test_every_router_module_has_an_importer() -> None:
    orphans = _routers_without_importer()
    assert not orphans, (
        "These modules define an APIRouter that no other app module imports, so none of their routes can be mounted. "
        "Mount the router or delete the module with its tests and docs:\n" + "\n".join(orphans)
    )
