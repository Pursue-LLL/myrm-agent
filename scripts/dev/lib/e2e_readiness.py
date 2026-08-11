"""Compatibility shim — module alias for e2e_core.readiness."""
import sys as _sys

from module_alias import install_module_alias as _install_module_alias

_install_module_alias(__name__, "e2e_core.readiness")

if __name__ == "__main__":
    raise _sys.exit(_sys.modules[__name__].main())
