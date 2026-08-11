"""Compatibility shim — module alias for browser_orchestrator.frontend_client_warmup. Do not add logic here."""
import importlib as _importlib

_impl = _importlib.import_module("browser_orchestrator.frontend_client_warmup")
# Copy the implementation's public symbols into this module's own namespace
# (globals()), which works for both normal import and module_from_spec callers.
for _k, _v in _impl.__dict__.items():
    if not _k.startswith("__") or _k in ("__all__", "__doc__", "__annotations__"):
        globals()[_k] = _v
globals()["__file__"] = _impl.__file__
