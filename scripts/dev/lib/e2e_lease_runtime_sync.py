"""Compatibility shim — live alias for ``e2e_core.lease_runtime_sync``."""

from module_alias import install_module_alias

install_module_alias(__name__, "e2e_core.lease_runtime_sync")
