"""Shared path bootstrap for the product dev-gate modules."""

from __future__ import annotations

from pathlib import Path


def scripts_dev_dir(anchor: Path) -> Path:
    """Return the nearest ``scripts/dev`` directory that owns wave state."""
    resolved = anchor.resolve()
    candidates = (resolved, *resolved.parents)
    for candidate in candidates:
        if (candidate / "wave_orchestrator").is_dir() and (candidate / "wave.sh").is_file():
            return candidate
    raise RuntimeError(f"cannot locate scripts/dev from {anchor}")
