"""Wiki Knowledge Governance domain facade.

[INPUT]
- app.services.wiki.governance.schemas::*
- app.services.wiki.governance.freshness_service::WikiGovernanceFreshnessService

[OUTPUT]
- Facade exports for governance schemas and domain service.

[POS]
Clean facade export for KnowledgeGovernanceWorkbenchExpiryArchiveRevival.
"""

from __future__ import annotations

from app.services.wiki.governance.freshness_service import (
    WikiGovernanceFreshnessService,
)
from app.services.wiki.governance.schemas import (
    ExpiringConceptInfo,
    GovernanceActionResult,
    GovernanceOverviewResult,
)

__all__ = [
    "ExpiringConceptInfo",
    "GovernanceActionResult",
    "GovernanceOverviewResult",
    "WikiGovernanceFreshnessService",
]
