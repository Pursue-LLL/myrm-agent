"""Server-layer tool-layer registration bootstrap.

[INPUT]
- myrm_agent_harness.agent.tool_management::register_tool_layers (POS: Tool layer
  priority registry batch API.)
- myrm_agent_harness.agent.tool_management::ToolRegistry (POS: Unified tool registry API.)
- myrm_agent_harness.agent.tool_management::ToolLayer (POS: Tool layer enum
  CORE=1, HIGH_PRIORITY=2, EXTENDED=3, EXTERNAL=4.)
- myrm_agent_harness.core.security.tool_registry::(SafetyMetadata, declare_external_tool) (POS: permission type
  and safety attributes of a tool the harness does not ship)

[OUTPUT]
- register_server_tools(): Idempotent registration of every server-specific
  `@tool` into the harness tool layer registry, and the governance declaration of the tools whose effects are known.

[POS]
Registers server-layer business tools (third-party SDKs, ChannelGateway outbound,
product media LangChain adapters, code graph navigation) into the harness registry at import time and explicit startup.
A tool without a declaration is governed as ``mcp_invoke`` (ask), which is right for the vendor tools that call
third-party services; ``code_graph_tool`` only reads the workspace and keeps its own index outside it, so it is
declared a ``file_read``.
"""

from __future__ import annotations

from myrm_agent_harness.agent.sub_agents.delegation_policy import (
    register_leaf_blocked_tools,
)
from myrm_agent_harness.agent.tool_management import ToolLayer, ToolRegistry
from myrm_agent_harness.core.security.tool_registry import SafetyMetadata, declare_external_tool

_SERVER_TOOL_LAYERS: dict[str, ToolLayer] = {
    # EXTERNAL: opt-in business tools that depend on server-specific SDKs/APIs.
    "channel_notify_tool": ToolLayer.EXTERNAL,
    "image_tool": ToolLayer.EXTERNAL,
    "video_tool": ToolLayer.EXTERNAL,
    "tts_generate": ToolLayer.EXTERNAL,
    "artifact_publish": ToolLayer.EXTERNAL,
    "code_graph_tool": ToolLayer.EXTERNAL,
}


def register_server_tools() -> None:
    """Register every server-defined tool into harness layer registry.

    Safe to call multiple times — `register_tool_layers` is idempotent.
    """
    ToolRegistry.register_external_layer_specs(_SERVER_TOOL_LAYERS)
    register_leaf_blocked_tools(frozenset({"channel_notify_tool"}))
    # Calls queue on the tool's own lock and the index is a cache outside the workspace.
    declare_external_tool(
        "code_graph_tool", "file_read", SafetyMetadata(is_read_only=True, is_concurrent_safe=True, is_idempotent=True)
    )


register_server_tools()
