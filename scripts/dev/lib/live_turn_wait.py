"""LIVE agent turn wait SSOT — steer-first recovery under parallel mux (R150/R153).

Dev Gate layer: shared by chrome_e2e LIVE tests; not harness/server business logic.
"""

from __future__ import annotations

from pathlib import Path


def parallel_live_agent_peer_count() -> int:
    """Wave/mux peers for LIVE post-send stall scaling."""
    try:
        from mux_load import snapshot_mux_load

        load = snapshot_mux_load()
        return max(int(load.wave_leases), int(load.mux_contexts))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    root = Path(__file__).resolve().parents[3]
    try:
        from stack_mutation_policy import wave_active_lease_count

        return wave_active_lease_count(root)
    except (ImportError, OSError, RuntimeError, ValueError):
        return 0


def live_empty_write_parallel_scaled_cap_sec(*, base: float) -> float:
    """Scale idle/stall caps under parallel LIVE_AGENT load."""
    peers = parallel_live_agent_peer_count()
    if peers < 2:
        return base
    scaled = base + peers * 10.0
    if peers >= 3:
        scaled = max(scaled, base + 40.0)
    return min(150.0, scaled)


def steer_empty_write_prompt(filename: str) -> str:
    return (
        "STEER: You MUST call file_write_tool exactly once now with "
        f"path {filename!r} and content '' (empty string). "
        "Do not reply with text only. "
        "Reply EMPTY_WRITE_DONE after the tool returns."
    )
