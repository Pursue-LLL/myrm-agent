from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.utils.response_utils import error_response, success_response
from app.services.agent.routing_advisor import analyze_provider_health

router = APIRouter()


@router.get("/provider-health")
async def get_provider_health(
    provider_name: str = Query(..., description="Name of the provider/model to check"),
    time_window_minutes: int = Query(5, description="Minutes to look back for analysis"),
) -> JSONResponse:
    """Get health analysis for a specific provider based on recent event logs."""
    try:
        health_info = await analyze_provider_health(provider_name, time_window_minutes)
        return success_response(data=health_info)
    except Exception as e:
        return error_response(message=f"Failed to analyze provider health: {str(e)}")
