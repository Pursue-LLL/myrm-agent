"""Compatibility shim — module alias for dev_gate.private_resource_controller.

The canonical implementation delegates capacity to
host_resource_governor.effective_private_capacity_credits.
"""
from module_alias import install_module_alias as _install_module_alias

_install_module_alias(__name__, "dev_gate.private_resource_controller")
