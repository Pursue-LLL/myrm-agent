"""Resolve MoA overlay model configs for agent-loop advisor fan-out.

[INPUT]
- app.services.agent.params::ModelSelection, _resolve_model_config
- app.core.channel_bridge.config_loader::load_user_configs

[OUTPUT]
- resolve_moa_overlay_models: overlay config dict + reference ModelConfig list
- build_moa_overlay_middleware: harness middleware or None when disabled

[POS]
Factory helper for agent-loop MoA overlay model resolution and middleware wiring.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.services.agent.params import ModelSelection, _resolve_model_config

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


def _cfg_float(raw: dict[str, object], key: str, default: float) -> float:
    val = raw.get(key, default)
    return float(val) if isinstance(val, (int, float)) else default


def _cfg_int(raw: dict[str, object], key: str, default: int) -> int:
    val = raw.get(key, default)
    return int(val) if isinstance(val, int) else default


def _cfg_int_or_none(raw: dict[str, object], key: str) -> int | None:
    val = raw.get(key)
    if val is None:
        return None
    if isinstance(val, int) and val > 0:
        return val
    return None


def _cfg_str(raw: dict[str, object], key: str, default: str) -> str:
    val = raw.get(key, default)
    return val if isinstance(val, str) else default


def _cfg_str_or_none(raw: dict[str, object], key: str) -> str | None:
    val = raw.get(key)
    return val if isinstance(val, str) and val else None


async def resolve_moa_overlay_models(
    engine_params: dict[str, object] | None,
) -> tuple[dict[str, object] | None, list[object] | None]:
    if not engine_params:
        return None, None
    raw_overlay = engine_params.get("moa_overlay")
    if not isinstance(raw_overlay, dict):
        return None, None
    if not raw_overlay.get("enabled"):
        return None, None

    overlay_config: dict[str, object] = raw_overlay
    ref_cfgs: list[object] | None = None
    try:
        from app.core.channel_bridge.config_loader import load_user_configs

        configs = await load_user_configs()
        pd = configs.providers_dict if configs else None
        ref_sels = raw_overlay.get("reference_model_selections", [])
        if isinstance(ref_sels, list):
            resolved: list[object] = []
            for sel in ref_sels:
                if isinstance(sel, dict):
                    ms = ModelSelection(**sel)
                    mc = await _resolve_model_config(ms, pd)
                    if mc:
                        resolved.append(mc)
            if resolved:
                ref_cfgs = resolved
    except Exception:
        logger.warning("Failed to resolve MoA overlay reference model selections")
    return overlay_config, ref_cfgs


async def build_moa_overlay_middleware(
    engine_params: dict[str, object] | None,
    *,
    unattended: bool = False,
    action_mode: str = "agent",
) -> Any | None:
    overlay_cfg, ref_cfgs = await resolve_moa_overlay_models(engine_params)
    if overlay_cfg is None:
        return None

    from myrm_agent_harness.agent.middlewares.moa_advisor_middleware import (
        create_moa_advisor_middleware,
    )
    from myrm_agent_harness.toolkits.llms import llm_manager
    from myrm_agent_harness.toolkits.llms.consensus.moa_overlay_types import (
        MoAOverlayConfig,
        PrivacyFilterMode,
    )

    reference_llms: list[BaseChatModel] = []
    for mc in ref_cfgs or []:
        try:
            llm = await llm_manager.get_llm_from_config(
                mc,
                api_keys=getattr(mc, "api_keys", None),
            )
            reference_llms.append(llm)
        except Exception:
            logger.warning(
                "MoA overlay: failed to create reference LLM for %s, skipping",
                getattr(mc, "model", "?"),
            )

    if not reference_llms:
        logger.warning("MoA overlay: no reference LLMs configured, skipping middleware")
        return None

    fanout_raw = _cfg_str(overlay_cfg, "fanout", "user_turn")
    fanout = fanout_raw if fanout_raw in ("user_turn", "per_iteration", "every_n") else "user_turn"
    privacy_raw = _cfg_str(overlay_cfg, "privacy_filter", "off")
    privacy: PrivacyFilterMode = (
        privacy_raw if privacy_raw in ("off", "display", "full") else "off"
    )

    config = MoAOverlayConfig(
        fanout=fanout,  # type: ignore[arg-type]
        every_n=_cfg_int(overlay_cfg, "every_n", 2),
        reference_temperature=_cfg_float(overlay_cfg, "reference_temperature", 0.6),
        min_successful=_cfg_int(overlay_cfg, "min_successful", 1),
        timeout_per_model=_cfg_float(overlay_cfg, "timeout_per_model", 120.0),
        timeout_total=_cfg_float(overlay_cfg, "timeout_total", 300.0),
        max_retries_per_model=_cfg_int(overlay_cfg, "max_retries_per_model", 2),
        reference_max_tokens=_cfg_int_or_none(overlay_cfg, "reference_max_tokens"),
        reference_reasoning_effort=_cfg_str_or_none(overlay_cfg, "reference_reasoning_effort"),
        privacy_filter=privacy,
    )

    return create_moa_advisor_middleware(
        reference_llms,
        config=config,
        unattended=unattended,
        action_mode=action_mode,
    )
