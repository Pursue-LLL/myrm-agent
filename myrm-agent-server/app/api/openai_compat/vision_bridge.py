"""Vision Bridge for LLM Passthrough — image-to-text conversion guardrail.

[INPUT]
- app.api.openai_compat.types::ChatMessage (POS: OpenAI request message type)
- app.core.channel_bridge.config_loader::_load_single_config (POS: user config loader)
- app.core.channel_bridge.model_resolver::resolve_model_config (POS: model resolution)
- myrm_agent_harness.toolkits.llms.vision.fallback_engine::VisionFallbackEngine (POS: image→text engine)

[OUTPUT]
- has_image_content: detect image_url blocks in messages
- bridge_vision: replace images with text descriptions when target model lacks vision

[POS]
Guardrail that intercepts image-bearing Passthrough requests destined for
non-vision models.  Uses the user-configured visionFallbackModel to describe
images via VisionFallbackEngine, then replaces image_url blocks with text
descriptions so the target model can process the request.  If no vision
fallback model is configured or if description fails, the original content
is preserved (fail-open).
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any

from app.api.openai_compat.types import ChatMessage

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
        VisionFallbackEngine,
    )

logger = logging.getLogger(__name__)

_MAX_BRIDGE_IMAGES = 5


def has_image_content(messages: list[ChatMessage]) -> bool:
    """Return True if any message contains image_url content blocks."""
    for msg in messages:
        if not isinstance(msg.content, list):
            continue
        for block in msg.content:
            if isinstance(block, dict) and block.get("type") == "image_url":
                return True
    return False


def _check_model_vision_support(litellm_model: str) -> bool:
    """Query litellm for model vision capability.

    Returns True if the model supports vision, False if it does not,
    and True (fail-open) if the capability cannot be determined.
    """
    try:
        import litellm

        info = litellm.get_model_info(litellm_model)
        supports = info.get("supports_vision")
        if supports is not None:
            return bool(supports)
    except Exception:
        logger.debug("Cannot determine vision support for %s, skipping bridge", litellm_model)
    return True


async def _load_vision_engine() -> VisionFallbackEngine | None:
    """Create a VisionFallbackEngine from the user's visionFallbackModel config.

    Returns None if not configured.
    """
    try:
        from app.core.channel_bridge.config_loader import _load_single_config
        from app.core.channel_bridge.model_resolver import resolve_model_config

        default_model_dict = await _load_single_config("default_model")
        if not default_model_dict:
            return None

        vision_cfg = default_model_dict.get("visionFallbackModel")
        if not vision_cfg or not isinstance(vision_cfg, dict):
            return None

        provider_id = vision_cfg.get("providerId", "")
        model_name = vision_cfg.get("model", "")
        if not provider_id or not model_name:
            return None

        providers_dict_raw = await _load_single_config("providers")
        providers_dict = providers_dict_raw if isinstance(providers_dict_raw, dict) else {}

        litellm_model = f"{provider_id}/{model_name}"
        model_cfg = resolve_model_config(providers_dict, model_override=litellm_model)

        from myrm_agent_harness.api import LLMConfig
        from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
            VisionFallbackEngine,
        )

        llm_config = LLMConfig(
            model=model_cfg.model,
            api_key=model_cfg.api_key,
            base_url=model_cfg.base_url,
        )
        return VisionFallbackEngine(llm_config)
    except Exception:
        logger.debug("Failed to create VisionFallbackEngine for bridge", exc_info=True)
        return None


async def _is_bridge_enabled() -> bool:
    """Check if visionBridgeEnabled is set in proxySettings."""
    try:
        from app.services.config.service import config_service

        record = await config_service.get("proxySettings")
        if record is None:
            return False
        value = record.value if hasattr(record, "value") else record
        if isinstance(value, dict):
            return bool(value.get("visionBridgeEnabled", False))
    except Exception:
        logger.debug("Failed to check vision bridge enabled status", exc_info=True)
    return False


async def bridge_vision(
    messages: list[ChatMessage],
    litellm_model: str,
) -> list[ChatMessage]:
    """Replace image_url blocks with text descriptions when the target model lacks vision.

    Conditions for bridging (checked in this order for minimal I/O):
    1. Messages contain image_url content
    2. Target model does not support vision (sync litellm check)
    3. visionBridgeEnabled is True in proxySettings (async DB read)
    4. visionFallbackModel is configured (async config load)

    If any condition fails, returns the original messages unchanged (fail-open).
    """
    if not has_image_content(messages):
        return messages

    if _check_model_vision_support(litellm_model):
        return messages

    if not await _is_bridge_enabled():
        return messages

    engine = await _load_vision_engine()
    if engine is None:
        return messages

    logger.info("Vision Bridge: converting images for non-vision model %s", litellm_model)

    bridged: list[ChatMessage] = []
    for msg in messages:
        if not isinstance(msg.content, list):
            bridged.append(msg)
            continue

        new_blocks: list[dict[str, Any]] = []
        image_count = 0

        for block in msg.content:
            if not isinstance(block, dict) or block.get("type") != "image_url":
                new_blocks.append(copy.deepcopy(block))
                continue

            if image_count >= _MAX_BRIDGE_IMAGES:
                new_blocks.append(copy.deepcopy(block))
                continue

            image_count += 1
            image_url_data = block.get("image_url", {})
            url = image_url_data.get("url", "") if isinstance(image_url_data, dict) else ""

            if not url or not url.startswith("data:"):
                new_blocks.append(copy.deepcopy(block))
                continue

            try:
                header, b64_data = url.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0] if ":" in header else "image/png"
                description = await engine.describe_image_b64(b64_data, mime_type)
                new_blocks.append({
                    "type": "text",
                    "text": f"[Image Description]: {description}",
                })
            except Exception:
                logger.warning("Vision Bridge: failed to describe image, preserving original")
                new_blocks.append(copy.deepcopy(block))

        bridged.append(ChatMessage(role=msg.role, content=new_blocks, name=msg.name))

    return bridged
