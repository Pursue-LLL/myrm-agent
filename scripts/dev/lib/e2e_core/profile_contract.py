"""Shared Chrome E2E profile reason contract.

The launcher and pytest plugin validate the same private-mode reason set. Keeping
the enum in the dev library prevents the two entry points from silently drifting.
"""

from __future__ import annotations

from typing import Final

PRIVATE_REASONS: Final[frozenset[str]] = frozenset(
    {
        "live_shpoib",
        "fault_injection",
        "exclusive_backend",
        "global_write_non_namespace",
    }
)

UNSUPPORTED_PRIVATE_REASONS: Final[frozenset[str]] = frozenset(
    {"process_isolation"}
)
