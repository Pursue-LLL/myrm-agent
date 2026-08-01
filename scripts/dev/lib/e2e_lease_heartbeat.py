"""Backward-compatible entry that delegates to unified heartbeat SSOT."""

from __future__ import annotations

from e2e_unified_heartbeat import heartbeat_once


def heartbeat_e2e_lease() -> None:
    """Extend wave lease and Dev Gate session progress during long E2E runs."""
    heartbeat_once()
