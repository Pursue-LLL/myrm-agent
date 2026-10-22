"""[INPUT]
- PromotedProjectResult, ProjectPromotionService

[OUTPUT]
- Facade exporting workspace promotion service

[POS]
Service layer module facade for workspace scratchpad promotion.
"""

from .service import (
    ProjectPromotionService,
    PromotedProjectResult,
)

__all__ = [
    "ProjectPromotionService",
    "PromotedProjectResult",
]
