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
    return resolve_allowed_local_attachment_path(path, allowed_roots) is not None


def resolve_allowed_local_attachment_path(
    path: str,
    allowed_roots: tuple[str, ...],
) -> str | None:
    """Resolve a local file path against allowed roots, returning normalized path or None.

    If ``path`` is relative, it is tested under each allowed root in sequence.
    If ``path`` is absolute, it is tested for membership under each allowed root.
    Returns the resolved string path if allowed and existing, or None.
    """
    if not path.strip() or not allowed_roots:
        return None

    candidate_path = Path(path).expanduser()

    # Case 1: Absolute path
    if candidate_path.is_absolute():
        try:
            resolved = candidate_path.resolve(strict=False)
        except (OSError, ValueError):
            return None
        for root in allowed_roots:
            if not root.strip():
                continue
            try:
                root_resolved = Path(root).expanduser().resolve(strict=False)
                if resolved.is_relative_to(root_resolved):
                    return str(candidate_path)
            except (OSError, ValueError):
                continue
        return None

    # Case 2: Relative path — probe against each allowed root
    for root in allowed_roots:
        if not root.strip():
            continue
        try:
            root_resolved = Path(root).expanduser().resolve(strict=False)
            resolved = (root_resolved / candidate_path).resolve(strict=False)
            if resolved.is_relative_to(root_resolved):
                return str(resolved)
        except (OSError, ValueError):
            continue

    return None

