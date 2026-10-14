"""Risk detection service.

Compiles and caches active risk rules as regex patterns, performs short-circuit
matching against text content, and records risk hits to the database.

Patterns are written for the ``regex`` package (everything ``re`` accepts) because only it can stop a match that
runs too long: ``detect`` runs on the event loop, on text any chat sender controls.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

import regex
from myrm_agent_harness.core.security.detection.custom_rules import pattern_problem
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import RiskHit, RiskRule

from .match_checks import is_confirmed_match

logger = logging.getLogger(__name__)

MAX_PATTERN_LENGTH = 4096

# Time one rule may spend on one text. A legitimate pattern needs milliseconds; a backtracking blow-up has no end, and
# ``detect`` holds the event loop meanwhile, so the budget bounds how long one message can stall the server. A rule that
# runs out of it counts as having matched (the text is not let through unchecked).
MATCH_TIMEOUT_SECONDS = 0.25

_TIMED_OUT_SUMMARY = "(matching timed out)"
_MAX_PREVIEW_SNIPPETS = 20
_SNIPPET_LENGTH = 80


def compile_pattern(pattern: str) -> regex.Pattern[str]:
    """Compile a rule pattern; ``ValueError`` says why it cannot be used.

    The engine builds every copy of a counted repeat when it compiles (``a{99999999}`` would take gigabytes), so the
    harness's size check comes before compiling.
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise ValueError(f"Pattern length {len(pattern)} exceeds limit {MAX_PATTERN_LENGTH}")
    problem = pattern_problem(pattern)
    if problem is not None:
        raise ValueError(f"Invalid regex pattern: {problem}")
    return regex.compile(pattern, regex.DOTALL)


def _abbreviate(snippet: str) -> str:
    if len(snippet) <= _SNIPPET_LENGTH:
        return snippet
    return snippet[:40] + "..." + snippet[-37:]


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
    compiled: regex.Pattern[str]


def _first_hit(rule: _CompiledRule, text: str) -> str | None:
    """The abbreviated text of the first confirmed match of *rule* in *text*, or None.

    A rule that cannot finish the text within the budget counts as a hit, so that a message built to stall a pattern
    is held by the rule instead of passing it.
    """
    try:
        for m in rule.compiled.finditer(text, timeout=MATCH_TIMEOUT_SECONDS):
            if is_confirmed_match(rule.rule_id, m.group()):
                return _abbreviate(m.group())
    except TimeoutError:
        logger.warning(
            "Risk rule %s did not finish a %d-character text in %.2fs; the text counts as its hit",
            rule.rule_id,
            len(text),
            MATCH_TIMEOUT_SECONDS,
        )
        return _TIMED_OUT_SUMMARY
    return None


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
            try:
                compiled_re = compile_pattern(rule.pattern)
            except ValueError as exc:
                logger.error("Skipping rule %s: %s", rule.rule_id, exc)
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
            snippet = _first_hit(rule, text)
            if snippet is None:
                continue

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

        Returns the matched text of the first matches, as ``detect`` would report it.
        Raises ValueError on an invalid pattern or one that cannot finish the text in time.
        """
        compiled = compile_pattern(pattern)
        snippets: list[str] = []
        try:
            for m in compiled.finditer(text, timeout=MATCH_TIMEOUT_SECONDS):
                snippets.append(_abbreviate(m.group()))
                if len(snippets) == _MAX_PREVIEW_SNIPPETS:
                    break
        except TimeoutError as exc:
            raise ValueError("Pattern took too long to match the sample text; simplify it") from exc
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
