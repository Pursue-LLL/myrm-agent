"""Wiki clip extension sync — UserConfig SSOT for MV3 clip target agent."""

from app.services.extension.clip.agent_config import (
    ExtensionClipAgentConfig,
    get_extension_clip_agent_config,
    set_extension_clip_agent_config,
)

__all__ = [
    "ExtensionClipAgentConfig",
    "get_extension_clip_agent_config",
    "set_extension_clip_agent_config",
]
