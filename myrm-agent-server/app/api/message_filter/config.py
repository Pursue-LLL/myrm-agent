"""Message filter configuration API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.database.models import MessageFilterConfig
from app.services.message_filter import ConfigVersionService

logger = logging.getLogger(__name__)

router = APIRouter()


class FilterConfigSchema(BaseModel):
    """Message filter configuration schema."""

    enabled: bool = Field(True, description="Whether filtering is enabled")
    pii_mode: str = Field("redact", description="PII detection mode: off | redact | block")
    whitelist_api_keys: list[str] = Field(default_factory=list, description="API keys that bypass filtering")
    audit_enabled: bool = Field(True, description="Whether to log filtering events")


class FilterConfigResponse(FilterConfigSchema):
    """Response schema for filter configuration."""

    id: int
    updated_by: str | None = None


@router.get("", response_model=FilterConfigResponse)
async def get_config(db: Annotated[AsyncSession, Depends(get_db)]) -> FilterConfigResponse:
    """Get current message filter configuration.

    Returns:
        Current filter configuration
    """
    try:
        stmt = select(MessageFilterConfig).limit(1)
        result = await db.execute(stmt)
        config = result.scalars().first()

        if config is None:
            config = MessageFilterConfig()
            db.add(config)
            await db.commit()
            await db.refresh(config)

        return FilterConfigResponse(
            id=config.id,
            enabled=config.enabled,
            pii_mode=config.pii_mode,
            whitelist_api_keys=config.whitelist_api_keys,
            audit_enabled=config.audit_enabled,
            updated_by=config.updated_by,
        )
    except Exception as e:
        logger.error(f"Failed to get config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get configuration") from e


@router.put("", response_model=FilterConfigResponse)
async def update_config(
    config_data: FilterConfigSchema,
    updated_by: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> FilterConfigResponse:
    """Update message filter configuration.

    Args:
        config_data: New configuration data
        updated_by: User making the change (for audit trail)
        db: Database session

    Returns:
        Updated filter configuration
    """
    try:
        stmt = select(MessageFilterConfig).limit(1)
        result = await db.execute(stmt)
        config = result.scalars().first()

        if config is None:
            config = MessageFilterConfig()
            db.add(config)

        config.enabled = config_data.enabled
        config.pii_mode = config_data.pii_mode
        config.whitelist_api_keys = config_data.whitelist_api_keys
        config.audit_enabled = config_data.audit_enabled
        config.updated_by = updated_by

        await db.commit()
        await db.refresh(config)

        version_service = ConfigVersionService(db)
        version = await version_service.save_version(config, updated_by=updated_by)
        logger.info(f"Config updated (v{version}) by {updated_by}")

        return FilterConfigResponse(
            id=config.id,
            enabled=config.enabled,
            pii_mode=config.pii_mode,
            whitelist_api_keys=config.whitelist_api_keys,
            audit_enabled=config.audit_enabled,
            updated_by=config.updated_by,
        )
    except Exception as e:
        logger.error(f"Failed to update config: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update configuration") from e
