"""Message filter rules API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.database.models import MessageFilterRule

logger = logging.getLogger(__name__)

router = APIRouter()


class FilterRuleSchema(BaseModel):
    """Message filter rule schema."""

    name: str = Field(..., description="Rule name")
    pattern_type: str = Field(..., description="Pattern type: regex | keyword | pattern")
    pattern: str = Field(..., description="Pattern to match")
    action: str = Field(..., description="Action to take: block | redact | alert")
    enabled: bool = Field(True, description="Whether rule is enabled")
    priority: int = Field(0, description="Rule priority (higher = earlier execution)")


class FilterRuleResponse(FilterRuleSchema):
    """Response schema for filter rule."""

    id: int


@router.get("", response_model=list[FilterRuleResponse])
async def list_rules(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[FilterRuleResponse]:
    """List all message filter rules.

    Args:
        enabled_only: If True, only return enabled rules
        db: Database session

    Returns:
        List of filter rules
    """
    try:
        stmt = select(MessageFilterRule).order_by(MessageFilterRule.priority.desc())
        if enabled_only:
            stmt = stmt.where(MessageFilterRule.enabled)

        result = await db.execute(stmt)
        rules = result.scalars().all()

        return [
            FilterRuleResponse(
                id=rule.id,
                name=rule.name,
                pattern_type=rule.pattern_type,
                pattern=rule.pattern,
                action=rule.action,
                enabled=rule.enabled,
                priority=rule.priority,
            )
            for rule in rules
        ]
    except Exception as e:
        logger.error(f"Failed to list rules: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list rules") from e


@router.post("", response_model=FilterRuleResponse, status_code=201)
async def create_rule(
    rule_data: FilterRuleSchema,
    db: AsyncSession = Depends(get_db),
) -> FilterRuleResponse:
    """Create a new filter rule.

    Args:
        rule_data: Rule data
        db: Database session

    Returns:
        Created filter rule
    """
    try:
        rule = MessageFilterRule(
            name=rule_data.name,
            pattern_type=rule_data.pattern_type,
            pattern=rule_data.pattern,
            action=rule_data.action,
            enabled=rule_data.enabled,
            priority=rule_data.priority,
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)

        logger.info(f"Created filter rule: {rule.name}")
        return FilterRuleResponse(
            id=rule.id,
            name=rule.name,
            pattern_type=rule.pattern_type,
            pattern=rule.pattern,
            action=rule.action,
            enabled=rule.enabled,
            priority=rule.priority,
        )
    except Exception as e:
        logger.error(f"Failed to create rule: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create rule") from e


@router.put("/{rule_id}", response_model=FilterRuleResponse)
async def update_rule(
    rule_id: int,
    rule_data: FilterRuleSchema,
    db: AsyncSession = Depends(get_db),
) -> FilterRuleResponse:
    """Update a filter rule.

    Args:
        rule_id: Rule ID
        rule_data: New rule data
        db: Database session

    Returns:
        Updated filter rule
    """
    try:
        stmt = select(MessageFilterRule).where(MessageFilterRule.id == rule_id)
        result = await db.execute(stmt)
        rule = result.scalars().first()

        if rule is None:
            raise HTTPException(status_code=404, detail="Rule not found")

        rule.name = rule_data.name
        rule.pattern_type = rule_data.pattern_type
        rule.pattern = rule_data.pattern
        rule.action = rule_data.action
        rule.enabled = rule_data.enabled
        rule.priority = rule_data.priority

        await db.commit()
        await db.refresh(rule)

        logger.info(f"Updated filter rule {rule_id}: {rule.name}")
        return FilterRuleResponse(
            id=rule.id,
            name=rule.name,
            pattern_type=rule.pattern_type,
            pattern=rule.pattern,
            action=rule.action,
            enabled=rule.enabled,
            priority=rule.priority,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update rule {rule_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update rule") from e


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a filter rule.

    Args:
        rule_id: Rule ID
        db: Database session
    """
    try:
        stmt = delete(MessageFilterRule).where(MessageFilterRule.id == rule_id)
        result = await db.execute(stmt)
        await db.commit()

        rc = getattr(result, "rowcount", None)
        if not isinstance(rc, int) or rc == 0:
            raise HTTPException(status_code=404, detail="Rule not found")

        logger.info(f"Deleted filter rule {rule_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete rule {rule_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete rule") from e
