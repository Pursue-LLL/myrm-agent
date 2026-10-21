"""Provider Balance REST API Router.

[INPUT]
- app.services.providers.balance_service::provider_balance_service
- fastapi::Query, Depends

[OUTPUT]
- GET /api/v1/providers/balance-gauges

[POS]
REST API endpoint exposing read-only multi-provider balance telemetry and soft warning states.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response
from app.services.providers.balance_service import provider_balance_service

router = APIRouter(prefix="/providers", tags=["provider-balance"])
logger = logging.getLogger(__name__)


@router.get("/balance-gauges")
async def get_provider_balance_gauges(
    force_refresh: bool = Query(default=False, description="Bypass 5-minute TTL cache with 10s cooldown"),
) -> JSONResponse:
    """Retrieve normalized live quota and balance metrics for all active providers."""
    try:
        gauges = await provider_balance_service.get_all_provider_balances(force_refresh=force_refresh)
        return success_response(gauges)
    except Exception as exc:
        logger.error("Failed to retrieve provider balance gauges: %s", exc, exc_info=True)
        raise internal_error("Failed to retrieve provider balance gauges", exception=exc) from exc
