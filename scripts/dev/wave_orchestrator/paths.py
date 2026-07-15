"""Resolved paths for the dev test wave orchestrator.

[INPUT]
- os.environ MYRM_DEV_STATE_DIR (POS: dev stack shared state root)

[OUTPUT]
- WavePaths dataclass — state_file and agent_dev_lib locations

[POS]
Path resolver for wave orchestrator. Keeps state under ~/.local/state/myrm-dev/.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WavePaths:
    state_dir: Path
    state_file: Path
    agent_dev_lib: Path
    server_python: Path


def resolve_wave_paths() -> WavePaths:
    dev_dir = Path(__file__).resolve().parent.parent
    agent_root = dev_dir.parent
    wave_override = os.environ.get("MYRM_WAVE_STATE_DIR", "").strip()
    if wave_override:
        state_dir = Path(wave_override).resolve()
    else:
        state_dir = Path(
            os.environ.get("MYRM_DEV_STATE_DIR", Path.home() / ".local/state/myrm-dev")
        ).resolve()
    server_python = agent_root / "myrm-agent-server" / ".venv" / "bin" / "python"
    return WavePaths(
        state_dir=state_dir,
        state_file=state_dir / "wave-orchestrator.json",
        agent_dev_lib=dev_dir / "lib",
        server_python=server_python,
    )
