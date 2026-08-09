"""Channel deliverable package exports.

[INPUT]
- deliverable.deep_links (POS: artifact deep links for IM delivery)
- deliverable.media (POS: attachment size cap and image compression)
- deliverable.scanner (POS: deliverable path token scan and resolve)

[OUTPUT]
- Re-exports for channel executor deliverable helpers

[POS]
Public surface for channel deliverable path scanning, media compression, and artifact links.
"""

from .deep_links import (
    build_artifact_deep_links,
    collect_channel_artifacts,
    fetch_artifact_versions,
)
from .media import (
    MAX_CHANNEL_ATTACHMENT_BYTES,
    compress_oversized_image,
    format_human_size,
    is_compressible_image,
)
from .scanner import (
    collect_deliverable_paths_from_text,
    extract_deliverable_path_tokens,
    resolve_chat_workspace_root,
    resolve_deliverable_path,
)

__all__ = [
    "MAX_CHANNEL_ATTACHMENT_BYTES",
    "build_artifact_deep_links",
    "collect_channel_artifacts",
    "collect_deliverable_paths_from_text",
    "compress_oversized_image",
    "extract_deliverable_path_tokens",
    "fetch_artifact_versions",
    "format_human_size",
    "is_compressible_image",
    "resolve_chat_workspace_root",
    "resolve_deliverable_path",
]
