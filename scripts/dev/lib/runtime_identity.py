"""Compatibility shim — module alias for e2e_core.runtime_identity.

The implementation emits CHROME_E2E_HEALTH_JSON with runtimeId, shellHot,
clientHot and stackEpoch fields.
"""
from module_alias import install_module_alias as _install_module_alias

_install_module_alias(__name__, "e2e_core.runtime_identity")
