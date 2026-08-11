"""Compatibility shim — module alias for e2e_core.host_resource_governor.

The canonical governor owns DOWNGRADE_LOAD_RATIO, UPGRADE_LOAD_RATIO and
COOLDOWN_SEC; this entry point exposes the same live module state.
"""
from module_alias import install_module_alias as _install_module_alias

_install_module_alias(__name__, "e2e_core.host_resource_governor")

# Keep AST-based compatibility checks tied to the canonical constants.
from e2e_core import host_resource_governor as _impl

DOWNGRADE_LOAD_RATIO = _impl.DOWNGRADE_LOAD_RATIO
UPGRADE_LOAD_RATIO = _impl.UPGRADE_LOAD_RATIO
COOLDOWN_SEC = _impl.COOLDOWN_SEC
