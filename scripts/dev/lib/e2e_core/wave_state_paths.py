"""Wave orchestrator JSON state file path SSOT.

[INPUT]
- wave_orchestrator.paths::resolve_wave_paths (POS: dev wave state dir resolver)

[OUTPUT]
- resolve_wave_state_file(): Path to wave-orchestrator.json

[POS]
Dev lib lazy-import bootstrap for wave state path. Single entry for lib/ and pytest guard consumers.
"""

from __future__ import annotations

import sys
from pathlib import Path


def resolve_wave_state_file() -> Path:
    dev_dir = Path(__file__).resolve().parent.parent
    dev_dir_str = str(dev_dir)
    if dev_dir_str not in sys.path:
        sys.path.insert(0, dev_dir_str)
    from wave_orchestrator.paths import resolve_wave_paths

    return resolve_wave_paths().state_file
