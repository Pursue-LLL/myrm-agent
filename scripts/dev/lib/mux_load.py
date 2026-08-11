"""Compatibility shim — live alias for ``mux.load``."""

from module_alias import install_module_alias

install_module_alias(__name__, "mux.load")
