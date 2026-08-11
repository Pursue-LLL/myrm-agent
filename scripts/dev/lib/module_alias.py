"""Small proxy-module helper for moved Dev Gate modules.

Compatibility imports must share the implementation module's globals so
monkeypatching either import path changes the same runtime object.
"""

from __future__ import annotations

import importlib
import sys
import types


class _ModuleAlias(types.ModuleType):
    """Forward public reads and writes to the canonical implementation."""

    _implementation: types.ModuleType

    def __getattribute__(self, name: str) -> object:
        if name.startswith("__") or name in {"_implementation", "_ModuleAlias"}:
            return super().__getattribute__(name)
        implementation = super().__getattribute__("_implementation")
        return getattr(implementation, name)

    def __setattr__(self, name: str, value: object) -> None:
        if name.startswith("__") or name in {"_implementation", "_ModuleAlias"}:
            super().__setattr__(name, value)
            return
        setattr(super().__getattribute__("_implementation"), name, value)

    def __delattr__(self, name: str) -> None:
        if name.startswith("__") or name in {"_implementation", "_ModuleAlias"}:
            super().__delattr__(name)
            return
        delattr(super().__getattribute__("_implementation"), name)

    def __dir__(self) -> list[str]:
        implementation = super().__getattribute__("_implementation")
        return sorted(set(super().__dir__()) | set(dir(implementation)))


def install_module_alias(module_name: str, implementation_name: str) -> None:
    """Turn the current compatibility module into a live implementation proxy."""
    implementation = importlib.import_module(implementation_name)
    module = sys.modules[module_name]
    module.__dict__["_implementation"] = implementation
    module.__class__ = _ModuleAlias
