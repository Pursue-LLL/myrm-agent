"""Risk governance API endpoints.

Provides CRUD for risk rules, batch toggle, rule testing, and hit audit log.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import RiskHit, RiskRule
from app.database.standard_responses import StandardSuccessResponse
from app.services.risk.detection import get_detection_service
from app.services.risk.rule_service import RiskRuleService, RuleValidationError

from .schemas import BatchImportRequest, BatchToggleRequest, RuleCreateRequest, RuleTestRequest, RuleUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter()

_rule_service = RiskRuleService()
_detection_service = get_detection_service()


def _rule_to_dict(rule: RiskRule) -> dict[str, object]:
    """Serialize a RiskRule ORM instance to dict."""
    return {
        "rule_id": rule.rule_id,
        "display_name": rule.display_name,
        "description": rule.description,
        "pattern": rule.pattern,
        "severity": rule.severity,
        "action": rule.action,
        "category": rule.category,
        "is_enabled": rule.is_enabled,
        "is_builtin": rule.is_builtin,
        "sort_order": rule.sort_order,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _hit_to_dict(hit: RiskHit) -> dict[str, object]:
    """Serialize a RiskHit ORM instance to dict."""
    return {
        "id": hit.id,
        "trace_id": hit.trace_id,
        "session_id": hit.session_id,
        "rule_id": hit.rule_id,
        "rule_name": hit.rule_name,
        "severity": hit.severity,
        "action": hit.action,
        "match_summary": hit.match_summary,
        "created_at": hit.created_at.isoformat() if hit.created_at else None,
    }


# ── Rule CRUD ──


@router.get("/rules", response_model=StandardSuccessResponse)
async def list_rules(
    category: str | None = Query(None),
    is_enabled: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """List all risk rules with optional filters."""
    rules = await _rule_service.list_rules(db, category=category, is_enabled=is_enabled)
    return success_response(data=[_rule_to_dict(r) for r in rules])


@router.get("/rules/{rule_id}", response_model=StandardSuccessResponse)
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get a single risk rule by rule_id."""
    rule = await _rule_service.get_rule(db, rule_id)
    if rule is None:
        raise not_found_error("Risk rule")
    return success_response(data=_rule_to_dict(rule))


@router.post("/rules", response_model=StandardSuccessResponse)
async def create_rule(
    body: RuleCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Create a new custom risk rule."""
    try:
        rule = await _rule_service.create_rule(
            db,
            rule_id=body.rule_id,
            display_name=body.display_name,
            pattern=body.pattern,
            severity=body.severity,
            action=body.action,
            category=body.category,
            description=body.description,
            sort_order=body.sort_order,
        )
        await db.commit()
        await _reload_detection(db)
        return success_response(data=_rule_to_dict(rule))
    except RuleValidationError as exc:
        raise validation_error(str(exc)) from exc


@router.patch("/rules/{rule_id}", response_model=StandardSuccessResponse)
async def update_rule(
    rule_id: str,
    body: RuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Update an existing risk rule."""
    try:
        rule = await _rule_service.update_rule(
            db,
            rule_id,
            display_name=body.display_name,
            description=body.description,
            pattern=body.pattern,
            severity=body.severity,
            action=body.action,
            category=body.category,
            is_enabled=body.is_enabled,
            sort_order=body.sort_order,
        )
    except RuleValidationError as exc:
        raise validation_error(str(exc)) from exc

    if rule is None:
        raise not_found_error("Risk rule")

    await db.commit()
    await _reload_detection(db)
    return success_response(data=_rule_to_dict(rule))


@router.delete("/rules/{rule_id}", response_model=StandardSuccessResponse)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Delete a custom risk rule. Built-in rules cannot be deleted."""
    try:
        deleted = await _rule_service.delete_rule(db, rule_id)
    except RuleValidationError as exc:
        raise validation_error(str(exc)) from exc

    if not deleted:
        raise not_found_error("Risk rule")

    await db.commit()
    await _reload_detection(db)
    return success_response(data={"deleted": True})


# ── Batch Operations ──


@router.post("/rules/batch-toggle", response_model=StandardSuccessResponse)
async def batch_toggle_rules(
    body: BatchToggleRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Batch enable or disable rules."""
    count = await _rule_service.batch_toggle(db, body.rule_ids, body.is_enabled)
    await db.commit()
    await _reload_detection(db)
    return success_response(data={"affected": count})


@router.post("/rules/batch-import", response_model=StandardSuccessResponse)
async def batch_import_rules(
    body: BatchImportRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Batch import custom rules. Skips duplicates."""
    try:
        rules_data = [r.model_dump() for r in body.rules]
        imported, skipped = await _rule_service.batch_import(db, rules_data)
        await db.commit()
        if imported > 0:
            await _reload_detection(db)
        return success_response(data={"imported": imported, "skipped": skipped})
    except RuleValidationError as exc:
        raise validation_error(str(exc)) from exc


# ── Rule Testing ──


@router.post("/rules/test", response_model=StandardSuccessResponse)
async def test_rule(
    body: RuleTestRequest,
) -> JSONResponse:
    """Test a regex pattern against sample text."""
    try:
        snippets = _detection_service.detect_preview(body.test_text, body.pattern)
    except ValueError as exc:
        raise validation_error(str(exc)) from exc
    return success_response(data={"matches": snippets, "count": len(snippets)})


# ── Risk Hits Audit ──


@router.get("/hits", response_model=StandardSuccessResponse)
async def list_hits(
    rule_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Query risk hit audit log with pagination."""
    hits, total = await _rule_service.get_hits(
        db,
        rule_id=rule_id,
        limit=limit,
        offset=offset,
    )
    return success_response(
        data={
            "list": [_hit_to_dict(h) for h in hits],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


# ── Seed ──


@router.post("/seed", response_model=StandardSuccessResponse)
async def seed_builtin_rules(
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Seed built-in risk rules (idempotent)."""
    count = await _rule_service.seed_builtin_rules(db)
    await db.commit()
    if count > 0:
        await _reload_detection(db)
    return success_response(data={"inserted": count})


# ── Internal helpers ──


async def _reload_detection(db: AsyncSession) -> None:
    """Reload the detection engine with latest rules."""
    try:
        await _detection_service.reload(db)
    except Exception:
        logger.exception("Failed to reload risk detection rules")
