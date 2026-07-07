"""Local attachment path policy for channel_notify_tool.

[INPUT]
- Agent declared_allowed_roots from factory wiring (POS: workspace path SSOT)

[OUTPUT]
- is_local_attachment_path_allowed(): True when resolved path is under an allowed root

[POS]
Server-side egress guard — aligns IM attachments with agent workspace boundaries.
"""

from __future__ import annotations

from pathlib import Path


def is_local_attachment_path_allowed(path: str, allowed_roots: tuple[str, ...]) -> bool:
    """Return True when ``path`` resolves under one of ``allowed_roots``."""
    if not path.strip() or not allowed_roots:
        return False

    try:
        resolved = Path(path).expanduser().resolve(strict=False)
    except (OSError, ValueError):
        return False

    for root in allowed_roots:
        if not root.strip():
            continue
        try:
            root_resolved = Path(root).expanduser().resolve(strict=False)
            if resolved.is_relative_to(root_resolved):
                return True
        except (OSError, ValueError):
            continue

    return False
