"""Risk detection service.

Compiles and caches active risk rules as regex patterns, performs short-circuit
matching against text content, and records risk hits to the database.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import RiskHit, RiskRule

logger = logging.getLogger(__name__)

MAX_PATTERN_LENGTH = 4096
REGEX_COMPILE_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class RiskMatch:
    """A single rule match result."""

    rule_id: str
    display_name: str
    severity: str
    action: str
    category: str
    match_summary: str


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Detection outcome for a piece of text."""

    blocked: bool
    matches: tuple[RiskMatch, ...]

    @property
    def highest_action(self) -> str:
        if not self.matches:
            return "allow"
        from .constants import RiskAction

        rank = RiskAction.RANK
        return max(self.matches, key=lambda m: rank.get(m.action, 0)).action


@dataclass
class _CompiledRule:
    """Internal compiled regex representation of a risk rule."""

    rule_id: str
    display_name: str
    severity: str
    action: str
    category: str
    compiled: re.Pattern[str]


@dataclass
class RiskDetectionService:
    """Stateful risk detection engine with compiled regex cache.

    Lifecycle:
    1. Call ``reload(session)`` to load rules from DB and compile patterns.
    2. Call ``detect(text)`` synchronously to match content.
    3. Call ``record_hits(session, ...)`` to persist matches.
    """

    _rules: list[_CompiledRule] = field(default_factory=list)
    _version: int = 0

    async def reload(self, session: AsyncSession) -> int:
        """Load enabled rules from DB and compile regex cache.

        Returns the number of successfully compiled rules.
        """
        stmt = select(RiskRule).where(RiskRule.is_enabled.is_(True)).order_by(RiskRule.sort_order)
        result = await session.execute(stmt)
        db_rules: Sequence[RiskRule] = result.scalars().all()

        compiled: list[_CompiledRule] = []
        for rule in db_rules:
            pattern_str = rule.pattern
            if len(pattern_str) > MAX_PATTERN_LENGTH:
                logger.warning(
                    "Skipping rule %s: pattern length %d exceeds limit %d",
                    rule.rule_id,
                    len(pattern_str),
                    MAX_PATTERN_LENGTH,
                )
                continue

            try:
                t0 = time.monotonic()
                compiled_re = re.compile(pattern_str, re.DOTALL)
                elapsed = time.monotonic() - t0
                if elapsed > REGEX_COMPILE_TIMEOUT_SECONDS:
                    logger.warning(
                        "Rule %s compiled in %.3fs (slow), consider simplifying pattern",
                        rule.rule_id,
                        elapsed,
                    )
            except re.error as exc:
                logger.error("Failed to compile rule %s: %s", rule.rule_id, exc)
                continue

            compiled.append(
                _CompiledRule(
                    rule_id=rule.rule_id,
                    display_name=rule.display_name,
                    severity=rule.severity,
                    action=rule.action,
                    category=rule.category,
                    compiled=compiled_re,
                )
            )

        self._rules = compiled
        self._version += 1
        logger.info("Risk rules reloaded: %d compiled, version=%d", len(compiled), self._version)
        return len(compiled)

    def detect(self, text: str) -> DetectionResult:
        """Match text against compiled rules (short-circuit on first block)."""
        if not text or not self._rules:
            return DetectionResult(blocked=False, matches=())

        matches: list[RiskMatch] = []
        blocked = False

        for rule in self._rules:
            m = rule.compiled.search(text)
            if m is None:
                continue

            snippet = m.group()
            if len(snippet) > 80:
                snippet = snippet[:40] + "..." + snippet[-37:]

            match = RiskMatch(
                rule_id=rule.rule_id,
                display_name=rule.display_name,
                severity=rule.severity,
                action=rule.action,
                category=rule.category,
                match_summary=snippet,
            )
            matches.append(match)

            if rule.action == "block":
                blocked = True
                break

        return DetectionResult(blocked=blocked, matches=tuple(matches))

    async def record_hits(
        self,
        session: AsyncSession,
        matches: Sequence[RiskMatch],
        trace_id: str,
        session_id: str | None = None,
    ) -> None:
        """Persist risk matches as audit records."""
        if not matches:
            return

        for m in matches:
            hit = RiskHit(
                trace_id=trace_id,
                session_id=session_id,
                rule_id=m.rule_id,
                rule_name=m.display_name,
                severity=m.severity,
                action=m.action,
                match_summary=m.match_summary,
            )
            session.add(hit)

        await session.flush()

    def detect_preview(self, text: str, pattern: str) -> list[str]:
        """Test a single regex pattern against text.

        Returns list of match snippets for rule preview/testing.
        Raises ValueError on invalid regex.
        """
        if len(pattern) > MAX_PATTERN_LENGTH:
            raise ValueError(f"Pattern length {len(pattern)} exceeds limit {MAX_PATTERN_LENGTH}")

        try:
            compiled = re.compile(pattern, re.DOTALL)
        except re.error as exc:
            raise ValueError(f"Invalid regex: {exc}") from exc

        found = compiled.findall(text)
        snippets: list[str] = []
        for item in found[:20]:
            s = item if isinstance(item, str) else str(item)
            if len(s) > 80:
                s = s[:40] + "..." + s[-37:]
            snippets.append(s)
        return snippets

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    @property
    def version(self) -> int:
        return self._version


_default_detection_service = RiskDetectionService()


def get_detection_service() -> RiskDetectionService:
    """Return the process-wide risk detection service singleton."""
    return _default_detection_service
