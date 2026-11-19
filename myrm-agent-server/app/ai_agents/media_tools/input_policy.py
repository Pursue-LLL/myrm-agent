"""The reference-resolution policy of the image and video tools and task executors.

[INPUT]
- myrm_agent_harness.toolkits.llms.media_inputs::MediaInputPolicy (POS: what a caller allows references to touch)
- app.core.media.reference::MEDIA_SCHEME, read_media_reference (POS: ``media://`` loader)
- app.ai_agents.media_tools.image_clamp::clamp_image_payload (POS: image downsampling and format normalization)
- app.config.deploy_mode::is_local_mode (POS: deployment mode)

[OUTPUT]
- build_media_input_policy(): policy for resolving image and video references

[POS]
The business-layer half of the single input resolver: it names the folders a reference may be read from (the agent's
workspace, which holds ``_uploaded/``), lets ``media://`` read straight from the media library, and downsizes every
image once on the way out. Local deployments may reach private addresses; everywhere else http(s) is SSRF-shielded.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from myrm_agent_harness.toolkits.llms.media_inputs import MediaInputPolicy

from app.ai_agents.media_tools.image_clamp import clamp_image_payload
from app.config.deploy_mode import is_local_mode
from app.core.media.reference import MEDIA_SCHEME, read_media_reference


def _downsize(data: bytes) -> bytes:
    return clamp_image_payload(data)[0]


def build_media_input_policy(allowed_roots: Sequence[str] = ()) -> MediaInputPolicy:
    """Policy for resolving references on behalf of an agent whose workspace folders are ``allowed_roots``."""
    return MediaInputPolicy(
        allowed_roots=tuple(Path(root) for root in allowed_roots),
        allow_private_networks=is_local_mode(),
        loaders={MEDIA_SCHEME: read_media_reference},
        image_hook=_downsize,
    )


__all__ = ["build_media_input_policy"]
