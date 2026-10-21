"""Wire routing package for business-layer model resolution."""

from app.core.wire.defaults import apply_wire_defaults
from app.core.wire.enrich import enrich_model_config
from app.core.wire.registry import (
    WireEndpointContext,
    normalize_model_name_for_wire,
    resolve_wire_protocol,
)

__all__ = [
    "WireEndpointContext",
    "apply_wire_defaults",
    "enrich_model_config",
    "normalize_model_name_for_wire",
    "resolve_wire_protocol",
]
