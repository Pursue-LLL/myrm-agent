import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models.agent_history import AgentProfileHistory

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/{agent_id}/history")
async def get_agent_history(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get the version history of an agent's profile."""
    try:
        result = await db.execute(
            select(AgentProfileHistory)
            .where(AgentProfileHistory.agent_id == agent_id)
            .order_by(desc(AgentProfileHistory.version))
            .limit(50)
        )
        history_records = result.scalars().all()
        
        history_list = [
            {
                "id": record.id,
                "version": record.version,
                "systemPrompt": record.system_prompt,
                "createdAt": record.created_at.isoformat() if record.created_at else None,
            }
            for record in history_records
        ]
        
        return success_response(data=history_list)
    except Exception as e:
        logger.error(f"Failed to fetch agent history: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
