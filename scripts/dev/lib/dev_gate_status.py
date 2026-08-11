"""Compatibility shim — live alias for ``dev_gate.status``."""

from module_alias import install_module_alias

install_module_alias(__name__, "dev_gate.status")
