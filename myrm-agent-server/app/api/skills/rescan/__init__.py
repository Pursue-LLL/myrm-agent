"""Skills supply-chain rescan API domain: rescan + advisory acknowledgment.

[INPUT]
- Rescan/advisory request payloads from the skills router (JSON body).
- Scan findings produced by ``app.core.skills.discovery.rescan_service``.

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``rescan`` subpackage:
  - rescan: ``router`` (APIRouter prefix `/rescan`) + rescan/report/advisory handlers
  - rescan_schemas: request/response Pydantic models

[POS]
Server business layer (Skills API). The rescan endpoints and their schemas are always wired
together and mounted via ``api.skills.router``, so they stay co-located under one facade.
"""

from app.api.skills.rescan.rescan import router
from app.api.skills.rescan.rescan_schemas import (
    AdvisoryAckRequest,
    AdvisoryAckResponse,
    AdvisoryUnackRequest,
    RescanReportResponse,
    RescanTriggerRequest,
    SkillRescanItemResponse,
)

__all__ = [
    "AdvisoryAckRequest",
    "AdvisoryAckResponse",
    "AdvisoryUnackRequest",
    "RescanReportResponse",
    "RescanTriggerRequest",
    "SkillRescanItemResponse",
    "router",
]
