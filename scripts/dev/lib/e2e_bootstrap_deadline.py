"""Compatibility shim — live alias for ``e2e_core.bootstrap_deadline``."""

import sys as _sys

from module_alias import install_module_alias

install_module_alias(__name__, "e2e_core.bootstrap_deadline")

if __name__ == "__main__":
    raise SystemExit(_sys.modules[__name__].main())
