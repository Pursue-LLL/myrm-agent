"""Compatibility shim — module alias for e2e_core.parallel_status.

The implementation emits E2E_CAP_HEADROOM: and E2E_PARALLEL_ACTIVE: lines.
"""
from module_alias import install_module_alias as _install_module_alias

_install_module_alias(__name__, "e2e_core.parallel_status")
