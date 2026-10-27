"""File meta-tool mount policy SSOT.

[OUTPUT]
- FileAccessMode: enum for the Turn1 file meta-tool mount surface

[POS]
Harness agent mount contract. Server ``tool_mount.resolve_agent_mount`` maps
product surfaces to FileAccessMode; ``get_meta_tools`` executes the mount.
"""

from __future__ import annotations

from enum import StrEnum


class FileAccessMode(StrEnum):
    """How file meta-tools mount on Turn1."""

    FULL = "full"
    WORKSPACE_READ_ONLY = "workspace_read_only"
    SPILL_AND_UPLOADS = "spill_and_uploads"
    NONE = "none"
