"""[INPUT]
- myrm_agent_harness.core.artifacts.constants::ArtifactType (POS: Artifact type mappings — framework-agnostic constants.)

[OUTPUT]
- _should_mount_ask_question_tool: Return True when structured HITL clarification is safe and product-appropriate.
- _configured_media_api_key: _configured_media_api_key
- _media_gateway_configured: _media_gateway_configured
- _is_media_credential_configured: _is_media_credential_configured
- _video_generation_credential_configured: _video_generation_credential_configured
- _select_image_constraints: Select optimal ImageConstraints based on model family.
- _get_artifact_push_fn: Create an artifact push callback for image/video generation tools.

[POS]
只放无 self 依赖的判断/构造工具，供各工具族 mixin 复用。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from myrm_agent_harness.core.artifacts.constants import ArtifactType

if TYPE_CHECKING:

    from app.ai_agents.agents import (
        VideoGenerationParams,
    )

logger = logging.getLogger(__name__)


def _should_mount_ask_question_tool(
    *,
    unattended_mode: bool,
    channel_name: str,
    prompt_mode: str,
    enable_structured_clarify: bool,
) -> bool:
    """Return True when structured HITL clarification is safe and product-appropriate."""
    if not enable_structured_clarify:
        return False
    if unattended_mode:
        return False
    if prompt_mode == "search":
        return False
    from myrm_agent_harness.agent.security.channel_presets import (
        ChannelType,
        resolve_channel_type,
    )

    return resolve_channel_type(channel_name) == ChannelType.WEB_CHAT


def _configured_media_api_key(api_key: str | None) -> bool:
    return bool((api_key or "").strip())


def _media_gateway_configured(gateway_config: dict[str, object] | None) -> bool:
    if not gateway_config:
        return False
    use_gateway = bool(gateway_config.get("use_gateway") or gateway_config.get("useGateway"))
    if not use_gateway:
        return False
    auth_token = gateway_config.get("auth_token") or gateway_config.get("authToken")
    gateway_url = gateway_config.get("gateway_url") or gateway_config.get("gatewayUrl")
    return bool(auth_token and str(auth_token).strip() and gateway_url and str(gateway_url).strip())


def _is_media_credential_configured(
    api_key: str | None,
    gateway_config: dict[str, object] | None,
) -> bool:
    return _configured_media_api_key(api_key) or _media_gateway_configured(gateway_config)


def _video_generation_credential_configured(params: VideoGenerationParams) -> bool:
    if _is_media_credential_configured(params.api_key, params.gateway_config):
        return True
    return any(
        _configured_media_api_key(str(fb.get("api_key")) if fb.get("api_key") is not None else None)
        for fb in params.fallback_providers
        if isinstance(fb, dict)
    )

def _select_image_constraints(model_name: str) -> object | None:
    """Select optimal ImageConstraints based on model family.

    Returns None to use defaults (Claude constraints).
    """
    from myrm_agent_harness.toolkits.computer_use.types import (
        CLAUDE_OPUS_47_IMAGE_CONSTRAINTS,
        GPT4V_IMAGE_CONSTRAINTS,
    )

    model_lower = model_name.lower()

    if any(k in model_lower for k in ("gpt-4", "gpt4", "o1", "o3", "o4")):
        return GPT4V_IMAGE_CONSTRAINTS

    if "opus-4" in model_lower or "claude-opus-4" in model_lower:
        return CLAUDE_OPUS_47_IMAGE_CONSTRAINTS

    return None


def _get_artifact_push_fn() -> Callable[[str, str, ArtifactType, str], None] | None:
    """Create an artifact push callback for image/video generation tools.

    Returns the ``push_inline_artifact`` function from the agent layer,
    or ``None`` when the agent runtime is unavailable.
    """
    try:
        from myrm_agent_harness.agent.artifacts import push_inline_artifact

        def _push(
            filename: str,
            preview_url: str,
            artifact_type: ArtifactType,
            content_type: str,
        ) -> None:
            push_inline_artifact(
                filename=filename,
                preview_url=preview_url,
                artifact_type=artifact_type,
                content_type=content_type,
            )

        return _push
    except Exception:
        return None
