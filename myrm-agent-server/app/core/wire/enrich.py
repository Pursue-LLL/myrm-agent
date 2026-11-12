"""Apply wire routing and defaults to a resolved ModelConfig.

[INPUT]
- app.core.types.business::ModelConfig (POS: Business-specific type definitions)
- app.core.wire.defaults::apply_wire_defaults (POS: Defaults layer of the wire routing: adds the request defaults that the `responses` wire needs for muse-spark models and the gateway headers and provider hint for Vercel AI Gateway endpoints, while explicit user values always win.)
- app.core.wire.registry::resolve_wire_protocol (POS: Routing table of the wire layer: on OpenCode-scoped endpoints (the OpenCode Go provider id, opencode.ai hosts or the local relay) it maps model-name patterns (gpt, grok and muse-spark to `responses`; minimax and qwen to `anthropic_messages`) to a wire protocol, and every other endpoint keeps the default wire protocol.)

[OUTPUT]
- enrich_model_config: returns a copy of the ModelConfig with the resolved wire protocol and the wire-aware model kwargs

[POS]
Entry point of the wire layer: the one call that model-config resolution makes to give a ModelConfig its wire protocol and
wire-specific model kwargs.
"""

from __future__ import annotations

from app.core.types import ModelConfig
from app.core.wire.defaults import apply_wire_defaults
from app.core.wire.registry import resolve_wire_protocol


def enrich_model_config(cfg: ModelConfig, *, provider_id: str | None = None) -> ModelConfig:
    wire = resolve_wire_protocol(cfg.model, cfg.base_url, provider_id=provider_id)
    model_kwargs = apply_wire_defaults(
        cfg.model,
        cfg.model_kwargs,
        wire,
        base_url=cfg.base_url,
        provider_id=provider_id,
    )
    return cfg.model_copy(update={"wire_protocol": wire, "model_kwargs": model_kwargs})
