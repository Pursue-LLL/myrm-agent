"""Channel and deployment mount resolution for GeneralAgent.

Decides which tools and system prompt appendices are safe and valid
to physically instantiate and inject based on the incoming channel type.

[INPUT]
- myrm_agent_harness.agent.security.channel_presets::ChannelType, resolve_channel_type
  (POS: Channel classification SSOT)
- app.config.computer_use_deploy::is_computer_use_deploy_supported
  (POS: Host OS & desktop deployment capability)

[OUTPUT]
- ResolvedMountPlan: dataclass containing physical mount booleans
- resolve_agent_mount(): channel_name + agent_wrapper -> ResolvedMountPlan

[POS]
Pure resolver layer between channel ingress and GeneralAgent factory wiring.
Prevents IM channels from leaking browser or desktop control tools/prompts and keeps the widget declaration
to the surface that can render it, eliminating prompt-token waste and tool-hallucination errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from myrm_agent_harness.agent.security.channel_presets import (
    ChannelType,
    resolve_channel_type,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedMountPlan:
    """Resolved physical tool mounting and prompt injection plan for an Agent."""

    mount_browser: bool
    mount_computer_use: bool
    mount_widget_capability: bool


def resolve_agent_mount(
    channel_name: str | None,
    agent_wrapper: object,
) -> ResolvedMountPlan:
    """Resolve physical mount decisions by intersecting profile flags with channel type.

    Rules:
    - Browser tools: Only mount in WEB_CHAT channels when profile has enable_browser=True.
    - Computer use: Only mount in WEB_CHAT channels when supported by host deploy mode; the desktop control
      rules in the system prompt are injected exactly when these tools are mounted.
    - Widget declaration: Only declare HTML widgets where they render (the web chat), and only for the
      conversational prompt modes; the search surface and naked mode never produce widgets.
    """
    effective_channel = channel_name or getattr(agent_wrapper, "channel_name", "web_chat") or "web_chat"
    channel_type = resolve_channel_type(effective_channel)

    is_web_chat = channel_type == ChannelType.WEB_CHAT

    # 1. Browser tool mounting
    enable_browser = bool(getattr(agent_wrapper, "enable_browser", False))
    mount_browser = is_web_chat and enable_browser

    # 2. Computer use tool mounting
    enable_computer_use = bool(getattr(agent_wrapper, "enable_computer_use", False))
    from app.config.computer_use_deploy import is_computer_use_deploy_supported

    can_deploy_cu = is_computer_use_deploy_supported()
    mount_computer_use = is_web_chat and enable_computer_use and can_deploy_cu

    # 3. Widget capability declaration; IM, cron, voice, kanban and eval channels all resolve to non-web-chat
    prompt_mode = getattr(agent_wrapper, "prompt_mode", "full")
    mount_widget_capability = is_web_chat and prompt_mode not in ("search", "naked")

    if not is_web_chat and (enable_browser or enable_computer_use):
        logger.info(
            "Channel '%s' (%s): safely omitted browser/desktop physical mount (profile: browser=%s, cu=%s)",
            effective_channel,
            channel_type.value,
            enable_browser,
            enable_computer_use,
        )

    return ResolvedMountPlan(
        mount_browser=mount_browser,
        mount_computer_use=mount_computer_use,
        mount_widget_capability=mount_widget_capability,
    )
