"""Resolve consensus model configs for agent-stream sessions.

[INPUT]
- app.services.agent.params::ModelSelection, _resolve_model_config
- app.core.channel_bridge.config_loader::load_user_configs

[OUTPUT]
- resolve_consensus_stream_models: consensus config + ref/aggregator model configs

[POS]
Orchestrator helper for consensus action_mode stream session setup.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.agent.params import ModelSelection, _resolve_model_config

if TYPE_CHECKING:
    from app.services.agent.params import AgentRequest

logger = logging.getLogger(__name__)


async def resolve_consensus_stream_models(
    request: AgentRequest,
) -> tuple[dict[str, object] | None, list[object] | None, object | None]:
    if request.action_mode != "consensus":
        return None, None, None
    ep = request.engine_params or {}
    raw_consensus = ep.get("consensus")
    if not isinstance(raw_consensus, dict):
        return None, None, None
    consensus_config: dict[str, object] = raw_consensus
    consensus_ref_cfgs: list[object] | None = None
    consensus_agg_cfg: object | None = None
    try:
        from app.core.channel_bridge.config_loader import load_user_configs

        configs = await load_user_configs()
        pd = configs.providers_dict if configs else None
        ref_sels = raw_consensus.get("reference_model_selections", [])
        if isinstance(ref_sels, list):
            resolved: list[object] = []
            for sel in ref_sels:
                if isinstance(sel, dict):
                    ms = ModelSelection(**sel)
                    mc = await _resolve_model_config(ms, pd)
                    if mc:
                        resolved.append(mc)
            if resolved:
                consensus_ref_cfgs = resolved
        agg_sel = raw_consensus.get("aggregator_model_selection")
        if isinstance(agg_sel, dict):
            ms = ModelSelection(**agg_sel)
            consensus_agg_cfg = await _resolve_model_config(ms, pd)
    except Exception:
        logger.warning("Failed to resolve consensus model selections")
    return consensus_config, consensus_ref_cfgs, consensus_agg_cfg
