"""Monkeypatch helper for the per-concern layout of this package.

A module that imports a name owns its own binding of it, so replacing the name in the module that defines it does not
reach the other modules that call it. ``patch_everywhere`` rebinds the name in every module that holds it, which is
what patching one module namespace achieves.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from types import ModuleType

import pytest

_PACKAGE = __name__.rpartition(".")[0]


def holders(name: str) -> list[ModuleType]:
    """Return the package and its submodules whose namespace binds ``name``."""
    package = sys.modules[_PACKAGE]
    modules = [package, *(importlib.import_module(f"{_PACKAGE}.{info.name}") for info in pkgutil.iter_modules(package.__path__))]
    return [module for module in modules if name in vars(module)]


def patch_everywhere(monkeypatch: pytest.MonkeyPatch, name: str, value: object) -> None:
    """Replace ``name`` with ``value`` in every module that holds it; ``monkeypatch`` restores them after the test."""
    targets = holders(name)
    if not targets:
        raise AttributeError(f"no module of {_PACKAGE} binds {name!r}")
    for module in targets:
        monkeypatch.setattr(module, name, value)
