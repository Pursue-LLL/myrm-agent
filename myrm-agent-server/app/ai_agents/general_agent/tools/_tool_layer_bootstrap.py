"""Server-layer tool-layer registration bootstrap.

[INPUT]
- myrm_agent_harness.agent.tool_management::register_tool_layers (POS: Tool layer
  priority registry batch API.)
- myrm_agent_harness.agent.tool_management::ToolRegistry (POS: Unified tool registry API.)
- myrm_agent_harness.agent.tool_management::ToolLayer (POS: Tool layer enum
  CORE=1, HIGH_PRIORITY=2, EXTENDED=3, EXTERNAL=4.)

[OUTPUT]
- register_server_tools(): Idempotent registration of every server-specific
  `@tool` into the harness tool layer registry.

[POS]
Registers server-layer business tools (third-party SDKs, ChannelGateway outbound,
product media LangChain adapters) into the harness registry at import time and explicit startup.
"""

from __future__ import annotations

from myrm_agent_harness.agent.sub_agents.delegation_policy import (
    register_leaf_blocked_tools,
)
from myrm_agent_harness.agent.tool_management import ToolLayer, ToolRegistry, register_tool_layers

_SERVER_TOOL_LAYERS: dict[str, ToolLayer] = {
    # EXTERNAL: opt-in business tools that depend on server-specific SDKs/APIs.
    "channel_notify_tool": ToolLayer.EXTERNAL,
    "image_tool": ToolLayer.EXTERNAL,
    "video_tool": ToolLayer.EXTERNAL,
    "tts_generate": ToolLayer.EXTERNAL,
    "artifact_publish": ToolLayer.EXTERNAL,
}


def register_server_tools() -> None:
    """Register every server-defined tool into harness layer registry.

    Safe to call multiple times — `register_tool_layers` is idempotent.
    """
    ToolRegistry.register_external_layer_specs(_SERVER_TOOL_LAYERS)
    register_leaf_blocked_tools(frozenset({"channel_notify_tool"}))


register_server_tools()

