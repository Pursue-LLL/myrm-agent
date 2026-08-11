"""Compatibility shim — module alias for browser_orchestrator.e2e. Do not add logic here."""
import importlib as _importlib
import sys as _sys

_impl = _importlib.import_module("browser_orchestrator.e2e")
_mod = _sys.modules[__name__]
for _k, _v in _impl.__dict__.items():
    if not _k.startswith("__") or _k in ("__all__", "__doc__", "__annotations__"):
        _mod.__dict__[_k] = _v
_mod.__dict__["__file__"] = _impl.__file__
