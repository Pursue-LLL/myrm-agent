"""Compatibility shim — live alias for dev_gate.cli."""

import sys as _sys

from module_alias import install_module_alias

install_module_alias(__name__, "dev_gate.cli")

if __name__ == "__main__":
    raise SystemExit(_sys.modules[__name__].main())
