"""Compatibility shim — module alias for browser_orchestrator.client."""
from module_alias import install_module_alias as _install_module_alias

_install_module_alias(__name__, "browser_orchestrator.client")
