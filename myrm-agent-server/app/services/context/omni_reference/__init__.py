"""[INPUT]
- .service::OmniReferenceResolverService
- .service::OmniEntityBrief
- .service::ResolvedSliceResult

[OUTPUT]
- Public re-exports for server context omni_reference package

[POS]
Facade for app.services.context.omni_reference.
"""

from app.services.context.omni_reference.service import (
    OmniReferenceResolverService,
    OmniEntityBrief,
    ResolvedSliceResult,
)

__all__ = [
    "OmniReferenceResolverService",
    "OmniEntityBrief",
    "ResolvedSliceResult",
]
