"""Message filter rule templates API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.database.models import MessageFilterRule

logger = logging.getLogger(__name__)

router = APIRouter()


class RuleTemplateSchema(BaseModel):
    """Rule template schema."""

    name: str
    pattern_type: str
    pattern: str
    action: str
    priority: int


class TemplateSchema(BaseModel):
    """Template schema."""

    id: str = Field(..., description="Template ID")
    name: str = Field(..., description="Template name")
    description: str = Field(..., description="Template description")
    rules: list[RuleTemplateSchema] = Field(..., description="Rules in template")


class ApplyTemplateResponse(BaseModel):
    """Response schema for template application."""

    success: bool
    rules_added: int
    message: str


PREDEFINED_TEMPLATES = {
    "pii-protection": TemplateSchema(
        id="pii-protection",
        name="PII Protection",
        description="Comprehensive PII detection and redaction rules",
        rules=[
            RuleTemplateSchema(
                name="Email Address",
                pattern_type="regex",
                pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                action="redact",
                priority=100,
            ),
            RuleTemplateSchema(
                name="Phone Number",
                pattern_type="regex",
                pattern=r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
                action="redact",
                priority=100,
            ),
            RuleTemplateSchema(
                name="SSN",
                pattern_type="regex",
                pattern=r"\b\d{3}-\d{2}-\d{4}\b",
                action="block",
                priority=200,
            ),
            RuleTemplateSchema(
                name="Credit Card",
                pattern_type="regex",
                pattern=r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
                action="block",
                priority=200,
            ),
        ],
    ),
    "credential-protection": TemplateSchema(
        id="credential-protection",
        name="Credential Protection",
        description="Detect and block API keys, tokens, and passwords",
        rules=[
            RuleTemplateSchema(
                name="API Key Pattern",
                pattern_type="regex",
                pattern=r"\b[Aa][Pp][Ii][-_\s]?[Kk][Ee][Yy][-_\s]?[:=]\s*['\"]?[\w-]{20,}['\"]?",
                action="block",
                priority=300,
            ),
            RuleTemplateSchema(
                name="Bearer Token",
                pattern_type="regex",
                pattern=r"\bBearer\s+[\w-]{20,}",
                action="block",
                priority=300,
            ),
            RuleTemplateSchema(
                name="Password in URL",
                pattern_type="regex",
                pattern=r"://[^:]+:[^@]+@",
                action="block",
                priority=300,
            ),
        ],
    ),
    "content-moderation": TemplateSchema(
        id="content-moderation",
        name="Content Moderation",
        description="Basic content moderation rules",
        rules=[
            RuleTemplateSchema(
                name="Profanity Filter",
                pattern_type="keyword",
                pattern="profane_word",
                action="redact",
                priority=50,
            ),
            RuleTemplateSchema(
                name="Spam Detection",
                pattern_type="keyword",
                pattern="spam_pattern",
                action="alert",
                priority=50,
            ),
        ],
    ),
}


@router.get("", response_model=list[TemplateSchema])
async def list_templates() -> list[TemplateSchema]:
    """List all available rule templates.

    Returns:
        List of available templates
    """
    return list(PREDEFINED_TEMPLATES.values())


@router.post("/{template_id}/apply", response_model=ApplyTemplateResponse)
async def apply_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApplyTemplateResponse:
    """Apply a rule template.

    Args:
        template_id: Template ID to apply
        db: Database session

    Returns:
        Application result
    """
    try:
        template = PREDEFINED_TEMPLATES.get(template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="Template not found")

        rules_added = 0
        for rule_schema in template.rules:
            rule = MessageFilterRule(
                name=rule_schema.name,
                pattern_type=rule_schema.pattern_type,
                pattern=rule_schema.pattern,
                action=rule_schema.action,
                enabled=True,
                priority=rule_schema.priority,
            )
            db.add(rule)
            rules_added += 1

        await db.commit()
        logger.info(f"Applied template {template_id}: {rules_added} rules added")

        return ApplyTemplateResponse(
            success=True,
            rules_added=rules_added,
            message=f"Successfully applied template '{template.name}' with {rules_added} rules",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply template {template_id}: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to apply template") from e
