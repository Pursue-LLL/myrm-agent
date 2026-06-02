"""Risk rule CRUD service.

Provides create, read, update, delete, batch toggle, and seed operations
for risk rules. Built-in rules can only be toggled, not deleted or pattern-modified.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import RiskHit, RiskRule

from .constants import RiskAction, RiskCategory, RiskSeverity, builtin_risk_rules
from .detection import MAX_PATTERN_LENGTH

logger = logging.getLogger(__name__)

VALID_SEVERITIES = frozenset({RiskSeverity.LOW, RiskSeverity.MEDIUM, RiskSeverity.HIGH})
VALID_ACTIONS = frozenset({RiskAction.ALLOW, RiskAction.BLOCK})
VALID_CATEGORIES = frozenset(
    {
        RiskCategory.PERSONAL,
        RiskCategory.COMPANY,
        RiskCategory.SECURITY,
        RiskCategory.FINANCE_LEGAL,
        RiskCategory.POLITICAL,
        RiskCategory.CUSTOMER,
        RiskCategory.CUSTOM,
    }
)


class RuleValidationError(Exception):
    """Raised when rule data fails validation."""


def _validate_pattern(pattern: str) -> None:
    """Validate regex pattern: syntax and length."""
    if not pattern or not pattern.strip():
        raise RuleValidationError("Pattern cannot be empty")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise RuleValidationError(f"Pattern length {len(pattern)} exceeds limit {MAX_PATTERN_LENGTH}")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise RuleValidationError(f"Invalid regex pattern: {exc}") from exc


def _validate_fields(
    severity: str,
    action: str,
    category: str,
) -> None:
    """Validate enum-like fields."""
    if severity not in VALID_SEVERITIES:
        raise RuleValidationError(f"Invalid severity '{severity}', must be one of {sorted(VALID_SEVERITIES)}")
    if action not in VALID_ACTIONS:
        raise RuleValidationError(f"Invalid action '{action}', must be one of {sorted(VALID_ACTIONS)}")
    if category not in VALID_CATEGORIES:
        raise RuleValidationError(f"Invalid category '{category}', must be one of {sorted(VALID_CATEGORIES)}")


class RiskRuleService:
    """CRUD service for risk rules."""

    async def list_rules(
        self,
        session: AsyncSession,
        category: str | None = None,
        is_enabled: bool | None = None,
    ) -> Sequence[RiskRule]:
        """List rules with optional category and enabled filters."""
        stmt = select(RiskRule).order_by(RiskRule.sort_order, RiskRule.id)
        if category is not None:
            stmt = stmt.where(RiskRule.category == category)
        if is_enabled is not None:
            stmt = stmt.where(RiskRule.is_enabled.is_(is_enabled))
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_rule(self, session: AsyncSession, rule_id: str) -> RiskRule | None:
        """Get a single rule by rule_id."""
        result = await session.execute(select(RiskRule).where(RiskRule.rule_id == rule_id))
        return result.scalar_one_or_none()

    async def create_rule(
        self,
        session: AsyncSession,
        *,
        rule_id: str,
        display_name: str,
        pattern: str,
        severity: str,
        action: str,
        category: str = RiskCategory.CUSTOM,
        description: str | None = None,
        sort_order: int = 0,
    ) -> RiskRule:
        """Create a custom risk rule."""
        _validate_pattern(pattern)
        _validate_fields(severity, action, category)

        existing = await self.get_rule(session, rule_id)
        if existing is not None:
            raise RuleValidationError(f"Rule '{rule_id}' already exists")

        rule = RiskRule(
            rule_id=rule_id,
            display_name=display_name,
            description=description,
            pattern=pattern,
            severity=severity,
            action=action,
            category=category,
            is_enabled=True,
            is_builtin=False,
            sort_order=sort_order,
        )
        session.add(rule)
        await session.flush()
        return rule

    async def update_rule(
        self,
        session: AsyncSession,
        rule_id: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        pattern: str | None = None,
        severity: str | None = None,
        action: str | None = None,
        category: str | None = None,
        is_enabled: bool | None = None,
        sort_order: int | None = None,
    ) -> RiskRule | None:
        """Update an existing rule. Built-in rules cannot change pattern."""
        rule = await self.get_rule(session, rule_id)
        if rule is None:
            return None

        if rule.is_builtin and pattern is not None:
            raise RuleValidationError("Cannot modify pattern of built-in rule")

        if pattern is not None:
            _validate_pattern(pattern)
            rule.pattern = pattern
        if severity is not None:
            if severity not in VALID_SEVERITIES:
                raise RuleValidationError(f"Invalid severity '{severity}'")
            rule.severity = severity
        if action is not None:
            if action not in VALID_ACTIONS:
                raise RuleValidationError(f"Invalid action '{action}'")
            rule.action = action
        if category is not None:
            if category not in VALID_CATEGORIES:
                raise RuleValidationError(f"Invalid category '{category}'")
            rule.category = category
        if display_name is not None:
            rule.display_name = display_name
        if description is not None:
            rule.description = description
        if is_enabled is not None:
            rule.is_enabled = is_enabled
        if sort_order is not None:
            rule.sort_order = sort_order

        await session.flush()
        return rule

    async def delete_rule(self, session: AsyncSession, rule_id: str) -> bool:
        """Delete a custom rule. Built-in rules cannot be deleted."""
        rule = await self.get_rule(session, rule_id)
        if rule is None:
            return False
        if rule.is_builtin:
            raise RuleValidationError("Cannot delete built-in rule; disable it instead")
        await session.delete(rule)
        await session.flush()
        return True

    async def batch_toggle(
        self,
        session: AsyncSession,
        rule_ids: list[str],
        is_enabled: bool,
    ) -> int:
        """Batch enable/disable rules. Returns count of affected rows."""
        if not rule_ids:
            return 0
        result = await session.execute(update(RiskRule).where(RiskRule.rule_id.in_(rule_ids)).values(is_enabled=is_enabled))
        await session.flush()
        if isinstance(result, CursorResult):
            return int(result.rowcount or 0)
        return 0


    async def batch_import(
        self,
        session: AsyncSession,
        rules_data: list[dict[str, str | int | bool | None]],
    ) -> tuple[int, list[str]]:
        """Batch import custom rules. Skips duplicates.

        Returns (imported_count, skipped_rule_ids).
        """
        existing_ids_result = await session.execute(
            select(RiskRule.rule_id).where(RiskRule.rule_id.in_([r["rule_id"] for r in rules_data]))
        )
        existing_ids = set(existing_ids_result.scalars().all())

        imported = 0
        skipped: list[str] = []
        for data in rules_data:
            rule_id = str(data["rule_id"])
            if rule_id in existing_ids:
                skipped.append(rule_id)
                continue

            _validate_pattern(str(data["pattern"]))
            _validate_fields(
                str(data.get("severity", "medium")),
                str(data.get("action", "block")),
                str(data.get("category", "custom")),
            )

            rule = RiskRule(
                rule_id=rule_id,
                display_name=str(data.get("display_name", rule_id)),
                description=data.get("description"),

                pattern=str(data["pattern"]),
                severity=str(data.get("severity", "medium")),
                action=str(data.get("action", "block")),
                category=str(data.get("category", "custom")),
                is_enabled=True,
                is_builtin=False,
                sort_order=int(data.get("sort_order", 0)),  # type: ignore[arg-type]
            )
            session.add(rule)
            imported += 1

        if imported > 0:
            await session.flush()
        return imported, skipped

    async def seed_builtin_rules(self, session: AsyncSession) -> int:
        """Seed built-in rules into DB. Skips rules that already exist.

        Returns the number of newly inserted rules.
        """
        defaults = builtin_risk_rules()
        existing_result = await session.execute(
            select(RiskRule.rule_id).where(RiskRule.rule_id.in_([d["rule_id"] for d in defaults]))
        )
        existing_ids = set(existing_result.scalars().all())

        inserted = 0
        for d in defaults:
            if d["rule_id"] in existing_ids:
                continue
            rule = RiskRule(
                rule_id=d["rule_id"],

                display_name=d["display_name"],

                description=d.get("description"),

                pattern=d["pattern"],

                severity=d["severity"],

                action=d["action"],

                category=d["category"],

                is_enabled=True,
                is_builtin=True,
                sort_order=d.get("sort_order", 0),

            )
            session.add(rule)
            inserted += 1

        if inserted > 0:
            await session.flush()
            logger.info("Seeded %d built-in risk rules", inserted)
        return inserted

    async def get_hits(
        self,
        session: AsyncSession,
        *,
        rule_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[RiskHit], int]:
        """Query risk hits with filtering and pagination.

        Returns (hits, total_count).
        """
        base = select(RiskHit)
        count_base = select(func.count(RiskHit.id))

        if rule_id is not None:
            base = base.where(RiskHit.rule_id == rule_id)
            count_base = count_base.where(RiskHit.rule_id == rule_id)

        total_result = await session.execute(count_base)
        total = total_result.scalar() or 0

        stmt = base.order_by(RiskHit.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        hits = result.scalars().all()

        return hits, total
