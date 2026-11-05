"""[INPUT]
- .model_plan::resolve_model_plan / finalize_model_plan (POS: model slot + fallback chain resolution)
- .sources::resolve_config_sources (POS: search / retrieval / MCP source resolution)
- .profile_apply::apply_agent_profile (POS: Agent profile capability envelope)
- .chat_context::resolve_chat_context (POS: chat workspace / access roots / shared memory)
- .tool_surface::resolve_tool_surface (POS: fast-search vs web-chat tool mount)

[OUTPUT]
- The conversion stages and their result types, re-exported for `params.converter`

[POS]
Aggregate exit of the conversion stage subpackage. Each module owns one stage; `converter.py` is
the only caller, so the stage order (model plan → sources → profile → model finalization → chat
context → tool surface) stays visible in one place instead of being spread across the package root.
"""

from __future__ import annotations

from .chat_context import ChatContext, resolve_chat_context
from .model_plan import ModelPlan, ModelResolver, finalize_model_plan, resolve_model_plan
from .profile_apply import ProfileContext, apply_agent_profile
from .sources import ConfigSources, resolve_config_sources
from .tool_surface import ToolSurface, resolve_tool_surface

__all__ = [
    "ChatContext",
    "ConfigSources",
    "ModelPlan",
    "ModelResolver",
    "ProfileContext",
    "ToolSurface",
    "apply_agent_profile",
    "finalize_model_plan",
    "resolve_chat_context",
    "resolve_config_sources",
    "resolve_model_plan",
    "resolve_tool_surface",
]
