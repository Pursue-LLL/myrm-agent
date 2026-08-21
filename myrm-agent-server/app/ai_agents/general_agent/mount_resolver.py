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
Prevents IM channels from leaking browser, desktop control, or CLI tools/prompts,
eliminating prompt-token waste and tool-hallucination errors.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

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
    mount_desktop_prompt: bool
    mount_cli_context: bool


def resolve_agent_mount(
    channel_name: str | None,
    agent_wrapper: Any,
) -> ResolvedMountPlan:
    """Resolve physical mount decisions by intersecting profile flags with channel type.

    Rules:
    - Browser tools: Only mount in WEB_CHAT channels when profile has enable_browser=True.
    - Computer use: Only mount in WEB_CHAT channels when supported by host deploy mode.
    - Desktop prompt: Only inject DESKTOP_CONTROL_RULES when computer use tools are mounted.
    - CLI context: Only inject CLI discovery context when not in untrusted IM channels.
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

    # 3. Desktop rules in System Prompt
    mount_desktop_prompt = mount_computer_use

    # 4. CLI discovery context in System Prompt
    # Only injected for web_chat/cron; IM channels must avoid polluting prompt with CLI tool signatures
    mount_cli_context = is_web_chat or channel_type == ChannelType.CRON

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
        mount_desktop_prompt=mount_desktop_prompt,
        mount_cli_context=mount_cli_context,
    )
