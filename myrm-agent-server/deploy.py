#!/usr/bin/env python3
"""Root deploy entrypoint — delegates to scripts/deploy.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_spec = importlib.util.spec_from_file_location("myrm_deploy_main", _SCRIPTS / "deploy.py")
if _spec is None or _spec.loader is None:
    raise RuntimeError("Failed to load scripts/deploy.py")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

main = _module.main

if __name__ == "__main__":
    main()
