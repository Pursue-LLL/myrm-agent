"""Risk detection service.

Compiles and caches active risk rules as regex patterns, performs short-circuit
matching against text content, and records risk hits to the database.

Patterns are read by the ``regex`` package, whose default mode reads ordinary ``re`` patterns the same way (it differs
on corner cases such as ``[[:alpha:]]``), because only it can stop a match that runs too long: the matched text is
anything a chat sender typed. A short text is matched on the event loop; a long one (``detect_async``) on a worker
thread, because the package lets go of the interpreter lock while it matches a ``str``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

import regex
from myrm_agent_harness.core.security.detection.custom_rules import pattern_problem
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import RiskHit, RiskRule

from .constants import INLINE_DETECT_CHARS
from .match_checks import first_confirmed_span

logger = logging.getLogger(__name__)

MAX_PATTERN_LENGTH = 4096

# How long a failed on-demand load of the rules (``RiskDetectionService.ensure_loaded``) is not tried again.
LOAD_RETRY_COOLDOWN_SECONDS = 30.0

# Time one rule may spend on one text. A legitimate pattern needs a fraction of a second even for a long text; a
# backtracking blow-up has no end, so the budget bounds how long one message can occupy the matcher. A rule that runs
# out of it counts as having matched (the text is not let through unchecked). ``MATCH_TIMEOUT_SECONDS`` is the budget
# of any text; a text of millions of characters (a pasted log) is allowed ``MATCH_SECONDS_PER_MEGACHAR`` for each
# million, which is about four times what the slowest built-in rule needs (0.13 s per million characters of log text,
# measured), so a slower host does not turn a harmless paste into a hit.
MATCH_TIMEOUT_SECONDS = 0.25
MATCH_SECONDS_PER_MEGACHAR = 0.5

# What a hit's ``match_summary`` holds: where the match lies, or that matching ran out of time. Never the matched text.
POSITION_SUMMARY_PREFIX = "chars:"
TIMED_OUT_SUMMARY = "(matching timed out)"
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


def match_budget(text_length: int) -> float:
    """Seconds one rule may spend matching a text of *text_length* characters."""
    return max(MATCH_TIMEOUT_SECONDS, MATCH_SECONDS_PER_MEGACHAR * text_length / 1_000_000)


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
    category: str
    match_summary: str


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Detection outcome for a piece of text."""

    blocked: bool
    matches: tuple[RiskMatch, ...]


@dataclass
class _CompiledRule:
    """Internal compiled regex representation of a risk rule."""

    rule_id: str
    display_name: str
    severity: str
    category: str
    compiled: regex.Pattern[str]


def _first_hit(rule: _CompiledRule, text: str) -> str | None:
    """Where the first confirmed match of *rule* lies in *text* (``chars:START-END``), or None.

    The summary names the position and never repeats the matched text: the rules exist to keep secrets and personal
    data from spreading, and the hit record would otherwise store them in the clear.

    A rule that cannot finish the text within the budget counts as a hit, so that a message built to stall a pattern
    is held by the rule instead of passing it.
    """
    budget = match_budget(len(text))
    try:
        span = first_confirmed_span(rule.rule_id, rule.compiled.finditer(text, timeout=budget))
    except TimeoutError:
        logger.warning(
            "Risk rule %s did not finish a %d-character text in %.2fs; the text counts as its hit",
            rule.rule_id,
            len(text),
            budget,
        )
        return TIMED_OUT_SUMMARY
    return None if span is None else f"{POSITION_SUMMARY_PREFIX}{span[0]}-{span[1]}"


@dataclass
class RiskDetectionService:
    """Stateful risk detection engine with compiled regex cache.

    Lifecycle:
    1. Call ``reload(session)`` to load rules from DB and compile patterns (startup does; ``ensure_loaded`` does when
       startup could not).
    2. Call ``detect(text)`` to match content in place, or ``await detect_async(text)`` when the text may be long.
    3. Call ``record_hits(session, ...)`` to persist matches.
    """

    _rules: list[_CompiledRule] = field(default_factory=list)
    _version: int = 0
    _load_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _next_load_attempt: float = 0.0

    async def ensure_loaded(self) -> None:
        """Load the rules from the database when ``reload`` has never run in this process.

        Startup gives up on loading after a few failed attempts, which would leave the process without any rule, and
        every text unscreened, until a restart; the first text screened afterwards loads them instead. A load that fails
        is not tried again for ``LOAD_RETRY_COOLDOWN_SECONDS``, so a database that stays down costs one attempt in that
        time, not one per message. Rules that were loaded and turned out to be none (all disabled) are not loaded again.
        """
        if self._version:
            return
        async with self._load_lock:
            if self._version or time.monotonic() < self._next_load_attempt:
                return
            try:
                from app.platform_utils import get_session_factory

                async with get_session_factory()() as db:
                    await self.reload(db)
            except Exception:
                self._next_load_attempt = time.monotonic() + LOAD_RETRY_COOLDOWN_SECONDS
                logger.error("Risk rules could not be loaded; texts are not screened until they are", exc_info=True)

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
                    category=rule.category,
                    compiled=compiled_re,
                )
            )

        self._rules = compiled
        self._version += 1
        logger.info("Risk rules reloaded: %d compiled, version=%d", len(compiled), self._version)
        return len(compiled)

    def detect(self, text: str) -> DetectionResult:
        """Match text against the compiled rules; the first rule that hits holds it."""
        if not text or not self._rules:
            return DetectionResult(blocked=False, matches=())

        for rule in self._rules:
            snippet = _first_hit(rule, text)
            if snippet is not None:
                match = RiskMatch(
                    rule_id=rule.rule_id,
                    display_name=rule.display_name,
                    severity=rule.severity,
                    category=rule.category,
                    match_summary=snippet,
                )
                return DetectionResult(blocked=True, matches=(match,))

        return DetectionResult(blocked=False, matches=())

    async def detect_async(self, text: str) -> DetectionResult:
        """``detect`` without holding the event loop for a long text.

        A long text is matched on a worker thread. ``reload`` replaces the whole rule list in one assignment, so a match
        in flight keeps reading the list it started with.
        """
        if len(text) <= INLINE_DETECT_CHARS:
            return self.detect(text)
        return await asyncio.to_thread(self.detect, text)

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
                match_summary=m.match_summary,
            )
            session.add(hit)

        await session.flush()

    def detect_preview(self, text: str, pattern: str) -> list[str]:
        """Test a single regex pattern against text.

        Returns the abbreviated text of the first matches, so the author of a rule sees what it catches in the sample.
        Raises ValueError on an invalid pattern or one that cannot finish the text in time.
        """
        compiled = compile_pattern(pattern)
        snippets: list[str] = []
        try:
            for m in compiled.finditer(text, timeout=match_budget(len(text))):
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
