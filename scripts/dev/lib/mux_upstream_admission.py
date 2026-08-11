"""Compatibility shim — module alias for mux.upstream_admission.

The canonical implementation delegates effective operation credits to
host_resource_governor.effective_browser_operation_credits.
"""
from module_alias import install_module_alias as _install_module_alias

_install_module_alias(__name__, "mux.upstream_admission")
