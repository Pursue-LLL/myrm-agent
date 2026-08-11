"""Compatibility shim — live alias for ``browser_orchestrator.e2e``."""

from module_alias import install_module_alias

install_module_alias(__name__, "browser_orchestrator.e2e")
