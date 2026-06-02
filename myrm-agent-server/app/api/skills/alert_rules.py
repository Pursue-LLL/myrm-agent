from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.database.models.skill_alert_rule import SkillAlertRule

router = APIRouter(prefix="/skill-alert-rules", tags=["skill-alert-rules"])

"""Skill Alert Rules API

REST endpoints for managing skill quality alert rules.

[POS]
Business layer API for alert rule configuration management (CRUD operations).
"""


class SkillAlertRuleCreate(BaseModel):
    """Schema for creating alert rule"""

    skill_id: str = Field(..., min_length=1, max_length=200)
    quality_threshold: float = Field(0.5, ge=0.0, le=1.0)
    channels: list[str] = Field(default_factory=list)
    enabled: bool = True
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None
    email_recipients: list[str] | None = None
    http_webhook_url: str | None = None


class SkillAlertRuleUpdate(BaseModel):
    """Schema for updating alert rule"""

    quality_threshold: float | None = Field(None, ge=0.0, le=1.0)
    channels: list[str] | None = None
    enabled: bool | None = None
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None
    email_recipients: list[str] | None = None
    http_webhook_url: str | None = None


class SkillAlertRuleResponse(BaseModel):
    """Schema for alert rule response"""

    skill_id: str
    quality_threshold: float
    channels: list[str]
    enabled: bool
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None
    email_recipients: list[str] | None = None
    http_webhook_url: str | None = None
    created_at: str
    updated_at: str


@router.post("", response_model=SkillAlertRuleResponse)
async def create_alert_rule(
    rule: SkillAlertRuleCreate,
    db: AsyncSession = Depends(get_db_session),
) -> SkillAlertRuleResponse:
    """Create or update alert rule for a skill

    If rule already exists for the skill, updates it.
    """
    existing = await db.get(SkillAlertRule, rule.skill_id)

    if existing:
        for key, value in rule.dict(exclude_unset=True).items():
            if key != "skill_id":
                setattr(existing, key, value)
        existing.updated_at = datetime.now()
        db_rule = existing
    else:
        db_rule = SkillAlertRule(**rule.dict())
        db.add(db_rule)

    await db.commit()
    await db.refresh(db_rule)

    return SkillAlertRuleResponse(
        skill_id=db_rule.skill_id,
        quality_threshold=db_rule.quality_threshold,
        channels=db_rule.channels,
        enabled=db_rule.enabled,
        slack_webhook_url=db_rule.slack_webhook_url,
        discord_webhook_url=db_rule.discord_webhook_url,
        email_recipients=db_rule.email_recipients,
        http_webhook_url=db_rule.http_webhook_url,
        created_at=db_rule.created_at.isoformat(),
        updated_at=db_rule.updated_at.isoformat(),
    )


@router.get("/{skill_id}", response_model=SkillAlertRuleResponse)
async def get_alert_rule(
    skill_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> SkillAlertRuleResponse:
    """Get alert rule for a skill

    If no rule exists, returns default rule (disabled).
    """
    from datetime import datetime

    rule = await db.get(SkillAlertRule, skill_id)

    if not rule:
        return SkillAlertRuleResponse(
            skill_id=skill_id,
            quality_threshold=0.5,
            channels=[],
            enabled=False,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

    return SkillAlertRuleResponse(
        skill_id=rule.skill_id,
        quality_threshold=rule.quality_threshold,
        channels=rule.channels,
        enabled=rule.enabled,
        slack_webhook_url=rule.slack_webhook_url,
        discord_webhook_url=rule.discord_webhook_url,
        email_recipients=rule.email_recipients,
        http_webhook_url=rule.http_webhook_url,
        created_at=rule.created_at.isoformat(),
        updated_at=rule.updated_at.isoformat(),
    )


@router.put("/{skill_id}", response_model=SkillAlertRuleResponse)
async def update_alert_rule(
    skill_id: str,
    update: SkillAlertRuleUpdate,
    db: AsyncSession = Depends(get_db_session),
) -> SkillAlertRuleResponse:
    """Update alert rule for a skill"""
    from datetime import datetime

    rule = await db.get(SkillAlertRule, skill_id)

    if not rule:
        raise HTTPException(status_code=404, detail=f"Alert rule not found for skill: {skill_id}")

    for key, value in update.dict(exclude_unset=True).items():
        setattr(rule, key, value)

    rule.updated_at = datetime.now()
    await db.commit()
    await db.refresh(rule)

    return SkillAlertRuleResponse(
        skill_id=rule.skill_id,
        quality_threshold=rule.quality_threshold,
        channels=rule.channels,
        enabled=rule.enabled,
        slack_webhook_url=rule.slack_webhook_url,
        discord_webhook_url=rule.discord_webhook_url,
        email_recipients=rule.email_recipients,
        http_webhook_url=rule.http_webhook_url,
        created_at=rule.created_at.isoformat(),
        updated_at=rule.updated_at.isoformat(),
    )


@router.delete("/{skill_id}")
async def delete_alert_rule(
    skill_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Delete alert rule for a skill"""
    rule = await db.get(SkillAlertRule, skill_id)

    if not rule:
        raise HTTPException(status_code=404, detail=f"Alert rule not found for skill: {skill_id}")

    await db.delete(rule)
    await db.commit()

    return {"status": "deleted", "skill_id": skill_id}


@router.get("")
async def list_alert_rules(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """List all alert rules

    Args:
        enabled_only: If True, only return enabled rules
    """
    from sqlalchemy import select

    from app.database.models.skill_alert_rule import SkillAlertRule

    query = select(SkillAlertRule)

    if enabled_only:
        query = query.where(SkillAlertRule.enabled == True)  # noqa: E712

    result = await db.execute(query)
    rules = result.scalars().all()

    return {
        "rules": [
            SkillAlertRuleResponse(
                skill_id=r.skill_id,
                quality_threshold=r.quality_threshold,
                channels=r.channels,
                enabled=r.enabled,
                slack_webhook_url=r.slack_webhook_url,
                discord_webhook_url=r.discord_webhook_url,
                email_recipients=r.email_recipients,
                http_webhook_url=r.http_webhook_url,
                created_at=r.created_at.isoformat(),
                updated_at=r.updated_at.isoformat(),
            )
            for r in rules
        ],
        "count": len(rules),
    }
