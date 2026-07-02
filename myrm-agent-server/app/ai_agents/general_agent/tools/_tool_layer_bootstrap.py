"""Server-layer tool-layer registration bootstrap.

[INPUT]
- myrm_agent_harness.agent.tool_management::register_tool_layer (POS: Tool layer
  priority registry API.)
- myrm_agent_harness.agent.tool_management::ToolLayer (POS: Tool layer enum
  CORE=1, COMMON=2, EXTENDED=3.)

[OUTPUT]
- register_server_tools(): Idempotent registration of every server-specific
  `@tool` into the harness `_TOOL_LAYERS` registry.

[POS]
Registers server-layer business tools (third-party SDKs, ChannelGateway outbound,
Canvas SDK) into the harness registry at import time.  Framework-native tools
(request_answer_user_tool, render_ui_tool, etc.) live in harness directly.
"""

from __future__ import annotations

from myrm_agent_harness.agent.tool_management import ToolLayer, register_tool_layer

_SERVER_TOOL_LAYERS: dict[str, ToolLayer] = {
    # EXTENDED: opt-in business tools that depend on server-specific SDKs/APIs.
    "x_search_tool": ToolLayer.EXTENDED,
    "browser_local_search_tool": ToolLayer.EXTENDED,
    "canvas_get_state": ToolLayer.EXTENDED,
    "canvas_get_selection": ToolLayer.EXTENDED,
    "canvas_insert_element": ToolLayer.EXTENDED,
    "channel_notify_tool": ToolLayer.EXTENDED,
}


def register_server_tools() -> None:
    """Register every server-defined tool into harness `_TOOL_LAYERS`.

    Safe to call multiple times — `register_tool_layer` is idempotent.
    """
    for name, layer in _SERVER_TOOL_LAYERS.items():
        register_tool_layer(name, layer)


register_server_tools()
