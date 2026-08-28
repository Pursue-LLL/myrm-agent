"""Apply wire routing and defaults to a resolved ModelConfig.

[POS]
app.core.wire.enrich

[INPUT]
- cfg (ModelConfig)
- provider_id (optional str)
"""

from __future__ import annotations

from app.core.types import ModelConfig
from app.core.wire.defaults import apply_wire_defaults
from app.core.wire.registry import resolve_wire_protocol


def enrich_model_config(cfg: ModelConfig, *, provider_id: str | None = None) -> ModelConfig:
    wire = resolve_wire_protocol(cfg.model, cfg.base_url, provider_id=provider_id)
    model_kwargs = apply_wire_defaults(cfg.model, cfg.model_kwargs, wire)
    return cfg.model_copy(update={"wire_protocol": wire, "model_kwargs": model_kwargs})
