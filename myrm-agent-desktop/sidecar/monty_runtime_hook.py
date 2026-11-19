"""PyInstaller runtime hook: point the Monty client at the worker that the bundle carries.

The client starts a worker executable for every script of ``browser_execute_script_tool``. Outside a bundle it finds
that executable in the environment's scripts directory or on PATH; a frozen app has neither, so without this hook every
script answers that the runtime is unavailable. ``MONTY_BIN`` is assigned, not defaulted: the sandbox that runs
model-written code must be the one that shipped, whatever the user's environment names.

[INPUT]
- os, sys (POS: the environment the client reads and the bundle's data directory, ``sys._MEIPASS``)

[OUTPUT]
- Import side effect: ``MONTY_BIN`` names the bundled worker (left alone when the bundle has none, which
  bundle_verify.py refuses to build)

[POS]
Runtime hook that build.py injects with ``--runtime-hook``; it runs before the sidecar entry imports the server, so the
client finds the worker the first time a script runs. The folder name must match ``MONTY_WORKER_DIR`` in
bundle_inventory.py, which tests/architecture/test_desktop_sidecar_monty_hook.py pins.
"""

import os
import sys

_worker = os.path.join(sys._MEIPASS, "monty_runtime", "monty.exe" if os.name == "nt" else "monty")
if os.path.isfile(_worker):
    os.environ["MONTY_BIN"] = _worker
