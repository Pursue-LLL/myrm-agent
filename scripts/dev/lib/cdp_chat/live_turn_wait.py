"""LIVE agent turn wait SSOT — steer-first recovery under parallel mux (R150/R153).

Dev Gate layer: shared by chrome_e2e LIVE tests; not harness/server business logic.
"""

from __future__ import annotations

from pathlib import Path


def parallel_live_agent_peer_count() -> int:
    """Wave/mux peers for LIVE post-send stall scaling."""
    try:
        from mux.load import snapshot_mux_load

        load = snapshot_mux_load()
        return max(int(load.wave_leases), int(load.mux_contexts))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    root = Path(__file__).resolve().parents[5]
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        return wave_active_lease_count(root)
    except (ImportError, OSError, RuntimeError, ValueError):
        return 0


LIVE_EMPTY_WRITE_STALL_CAP_MAX_SEC: float = 240.0
LIVE_EMPTY_WRITE_STALL_HEAVY_PEER_THRESHOLD: int = 5


def live_empty_write_steer_attempts_cap() -> int:
    """R173: repeat steer under parallel when first steer does not invoke tool."""
    return 2 if parallel_live_agent_peer_count() >= 2 else 1


def live_empty_write_steer_retry_idle_sec() -> float:
    """Idle before re-steer after first steer attempt under parallel mux load."""
    return 60.0 if parallel_live_agent_peer_count() >= 2 else 45.0


def live_empty_write_ui_nudge_allowed_after_steer(*, idle_sec: float) -> bool:
    """Allow UI nudge after steer when stream idle long enough under parallel."""
    peers = parallel_live_agent_peer_count()
    if peers < 2:
        return True
    return idle_sec >= 90.0


def live_empty_write_parallel_scaled_cap_sec(*, base: float) -> float:
    """Scale idle/stall caps under parallel LIVE_AGENT load."""
    peers = parallel_live_agent_peer_count()
    if peers < 2:
        return base
    if peers >= LIVE_EMPTY_WRITE_STALL_HEAVY_PEER_THRESHOLD:
        scaled = base + peers * 15.0
        floor = base + 90.0
        ceiling = min(LIVE_EMPTY_WRITE_STALL_CAP_MAX_SEC, scaled + 30.0)
        return min(ceiling, max(scaled, floor))
    scaled = base + peers * 10.0
    if peers >= 3:
        scaled = max(scaled, base + 40.0)
    return min(180.0, scaled)


def steer_empty_write_prompt(filename: str) -> str:
    return (
        "STEER: You MUST call file_write_tool exactly once now with "
        f"path {filename!r} and content '' (empty string). "
        "Do not reply with text only. "
        "Reply EMPTY_WRITE_DONE after the tool returns."
    )
