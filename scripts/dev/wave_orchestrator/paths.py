"""Resolved paths for the dev test wave orchestrator.

[INPUT]
- os.environ MYRM_DEV_STATE_DIR, MYRM_WAVE_STATE_DIR (POS: dev stack shared state root; WAVE wins)

[OUTPUT]
- WavePaths dataclass — state_file and agent_dev_lib locations
- resolve_dev_state_dir() — shared mux admission state root SSOT

[POS]
Path resolver for wave orchestrator. Keeps state under ~/.local/state/myrm-dev/.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WavePaths:
    state_dir: Path
    state_file: Path
    agent_dev_lib: Path
    server_python: Path


def _wave_is_open(state_dir: Path) -> bool:
    state_file = state_dir / "wave-orchestrator.json"
    if not state_file.is_file():
        return False
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    wave = payload.get("wave")
    return isinstance(wave, dict) and str(wave.get("status", "")).strip() == "open"


def _real_user_home() -> Path:
    home = os.environ.get("HOME", "").strip()
    if home and "/.cursor2" not in home:
        return Path(home).expanduser().resolve()
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()
    except (ImportError, KeyError, OSError):
        return Path.home().expanduser().resolve()


def _default_state_dir() -> Path:
    return _real_user_home() / ".local/state/myrm-dev"


def _state_dir_candidates() -> tuple[Path, ...]:
    ordered: list[Path] = []
    seen: set[str] = set()
    for raw in (
        os.environ.get("MYRM_WAVE_STATE_DIR", "").strip(),
        os.environ.get("MYRM_DEV_STATE_DIR", "").strip(),
    ):
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    for fallback in (_default_state_dir(), Path.home().expanduser().resolve() / ".local/state/myrm-dev"):
        key = str(fallback)
        if key not in seen:
            seen.add(key)
            ordered.append(fallback)
    return tuple(ordered)


def _is_cursor2_shadow(path: Path) -> bool:
    """True when path is inside a Cursor-sandbox redirected HOME shadow dir.

    Cursor redirects HOME to ~/.cursor2 so default-inferred state dirs land under
    the shadow; the real wave lives under the real user's home. Such paths must
    keep participating in the open-wave scan (R287). Everything else that was
    explicitly set (isolated runtime state dirs, real-home shared dir) is SSOT.
    """
    return any(part.lower() == "cursor2" for part in path.parts)


def resolve_wave_paths() -> WavePaths:
    dev_dir = Path(__file__).resolve().parent.parent
    agent_root = dev_dir.parent
    candidates = _state_dir_candidates()
    explicit = os.environ.get("MYRM_WAVE_STATE_DIR", "").strip()
    if not explicit:
        explicit = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    if explicit and _is_cursor2_shadow(Path(explicit).expanduser().resolve()):
        explicit = ""
    if explicit:
        # Explicitly set WAVE/DEV state dir is the caller's SSOT (isolated runtimes
        # carry their own wave-orchestrator.json). Never fall back to another
        # candidate just because this wave is closed while a shared wave is open —
        # otherwise isolated lease validation lands on the shared wave file.
        state_dir = Path(explicit).expanduser().resolve()
    else:
        state_dir = candidates[0] if candidates else _default_state_dir()
        for candidate in candidates:
            if _wave_is_open(candidate):
                state_dir = candidate
                break
    server_python = agent_root / "myrm-agent-server" / ".venv" / "bin" / "python"
    return WavePaths(
        state_dir=state_dir,
        state_file=state_dir / "wave-orchestrator.json",
        agent_dev_lib=dev_dir / "lib",
        server_python=server_python,
    )


def resolve_dev_state_dir() -> Path:
    """Shared dev stack state root (WAVE override wins over DEV)."""
    return resolve_wave_paths().state_dir
