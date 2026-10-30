"""Trace Analyzer for Skill Evolution.

[INPUT]
- agent.event_log::sanitize_event_data (POS: The redaction every event payload passes before it is written; applied again to the events and the tool names a prompt is built from.)
- agent.event_log.protocol::EventLogBackend (POS: Protocol contract. Framework provides FileEventLogBackend; business layer may extend with SQLite / PostgreSQL implementations.)
- agent.event_log.analytics_queries::get_session_summary (POS: Read-side analytics helpers for ``EventLogger``.)
- agent.event_log.analytics_queries::get_tool_usage_stats (POS: Read-side analytics helpers for ``EventLogger``.)
- agent.event_log.types::EventFilter (POS: Single source of truth for event log data structures.)

[OUTPUT]
- TraceAnalyzer: Builds the English failure report a repair prompt carries from the end of a session's event log.

[POS]
Trace Analyzer for Skill Evolution. Progressive disclosure: overview, failure mode, tool stats, clustered errors, recent tool events.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from myrm_agent_harness.agent.event_log import sanitize_event_data
from myrm_agent_harness.agent.event_log.analytics_queries import (
    get_session_summary,
    get_tool_usage_stats,
)
from myrm_agent_harness.agent.event_log.protocols import EventLogBackend
from myrm_agent_harness.agent.event_log.types import (
    EventFilter,
    EventPayload,
    SessionAnalytics,
    StructuredEvent,
    ToolUsageStats,
)

logger = logging.getLogger(__name__)

_FAILURE_EVENT_TYPES = frozenset({"tool_failure", "tool_timeout"})
_MAX_ERROR_EVENTS = 20
_MAX_ERROR_CLUSTERS = 10
_MAX_TOOL_STATS = 5
_RECENT_TOOL_EVENTS = 5
_MAX_TAKEOVER_EVENTS = 3
_TAKEOVER_ARIA_CHARS = 800
_ERROR_MESSAGE_CHARS = 200
_CHARS_PER_TOKEN = 4
_DEFAULT_TOKEN_BUDGET = 1500
_CLUSTER_SIMILARITY = 0.8
_TIMEOUT_MODE_MIN_EVENTS = 4

# Failure mode -> (likely cause, suggested fix) lines the report prints under the mode.
_FAILURE_GUIDANCE: dict[str, tuple[str, str]] = {
    "timeout": (
        "A tool call timed out.",
        "Raise the timeout, or reduce the algorithmic cost.",
    ),
    "permission": (
        "Permission was missing or access was denied.",
        "Check file and directory permissions, or the API credentials.",
    ),
    "tool_error": (
        "A tool call failed.",
        "Check that the arguments match the tool schema, and the logic for flaws.",
    ),
}


def _stored_tool_name(name: object) -> str:
    """A tool name from the summary helpers, which read the log as stored, redacted for the prompt.

    A call the model wrote badly is kept whole, arguments included, where the name belongs.
    """
    return str(sanitize_event_data({"tool_name": str(name)}).get("tool_name", ""))


def _redacted(events: Sequence[StructuredEvent]) -> list[StructuredEvent]:
    """The events with the redaction of the write path applied again.

    The log is the record and may predate a rule; what these events hold goes into a model prompt. Callers slice to
    the events the prompt shows first: the redaction runs on the event loop and costs about half a millisecond each.
    """
    return [
        event.model_copy(update={"data": EventPayload.model_validate(sanitize_event_data(event.data.model_dump()))})
        for event in events
    ]


@dataclass(frozen=True, slots=True)
class _TraceEvidence:
    """What the report is written from: the session summary and the end of its tool events."""

    summary: SessionAnalytics
    tool_stats: list[ToolUsageStats]
    error_events: list[StructuredEvent]
    recent_events: list[StructuredEvent]
    tool_event_count: int


class TraceAnalyzer:
    """Builds the failure report a repair prompt carries, from the end of a session's event log.

    Progressive disclosure: Overview -> Failure Analysis -> Tool Stats -> Error Details -> Run Totals -> Recent Tool Events.
    """

    def __init__(self, backend: EventLogBackend) -> None:
        self._backend = backend

    async def extract_trajectory(
        self, session_id: str, skill_id: str, max_token_budget: int = _DEFAULT_TOKEN_BUDGET
    ) -> str:
        """The report of the run in which ``skill_id`` failed, with the human takeover evidence of the session.

        A chat's log holds every turn of the chat, so the report reads the end of the log: the last tool events and
        the last failures, not the first ones a limited read returns. The report text is held to ``max_token_budget``
        (estimated, 4 characters per token); the takeover evidence follows it.

        Returns:
            The report, or an empty string when the log holds no events for the session so the caller keeps its own
            description of the failure.
        """
        start_time = time.time()

        if not self._backend:
            return "Trace analysis unavailable (no EventLogBackend)."

        # The summary supplies duration, distinct tools and token use; one event is enough to tell the log is not empty.
        summary = await get_session_summary(self._backend, session_id, events_limit=1, timeline_limit=1)
        if not summary.events_timeline:
            return ""

        tool_stats = await get_tool_usage_stats(self._backend, session_id)
        tool_events = await self._backend.get_events(
            session_id,
            EventFilter(event_types=frozenset({"tool_start", "tool_end", "tool_failure", "tool_timeout"})),
        )
        failures = [event for event in tool_events if event.event_type in _FAILURE_EVENT_TYPES]
        evidence = _TraceEvidence(
            summary=summary,
            tool_stats=tool_stats,
            error_events=_redacted(failures[-_MAX_ERROR_EVENTS:]),
            recent_events=_redacted(tool_events[-_RECENT_TOOL_EVENTS:]),
            tool_event_count=len(tool_events),
        )

        report = self._format_for_llm(
            evidence,
            self._analyze_failure_mode(evidence.tool_stats, evidence.error_events),
            skill_id,
            max_token_budget,
        )
        takeover = await self._extract_takeover_evidence(session_id)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(f"TraceAnalyzer executed in {elapsed_ms:.1f}ms for session {session_id}")

        return report + takeover

    async def _extract_takeover_evidence(self, session_id: str) -> str:
        """Extract human takeover traces as supplementary evidence for evolution.

        When a user took over during the same session, their actions provide
        a concrete demonstration of the correct approach.
        """
        if not self._backend:
            return ""

        takeover_events = await self._backend.get_events(
            session_id,
            EventFilter(event_types=frozenset({"takeover_trace"})),
        )

        if not takeover_events:
            return ""

        lines = ["\n\n## Human Takeover Evidence"]
        for evt in _redacted(takeover_events[-_MAX_TAKEOVER_EVENTS:]):
            reason = evt.data.get("reason", "")
            pre_url = evt.data.get("pre_url", "")
            post_url = evt.data.get("post_url", "")
            duration = evt.data.get("duration_s", 0)
            post_aria = str(evt.data.get("post_aria_tree", ""))

            lines.append(f"\n### Takeover (duration: {duration}s)")
            if reason:
                lines.append(f"- Reason: {reason}")
            if pre_url != post_url:
                lines.append(f"- Page change: {pre_url} -> {post_url}")
            elif pre_url:
                lines.append(f"- Page: {pre_url} (URL unchanged, DOM structure changed)")
            if post_aria:
                lines.append(f"- Page state after the takeover:\n```\n{post_aria[:_TAKEOVER_ARIA_CHARS]}\n```")

        return "\n".join(lines)

    def _analyze_failure_mode(
        self, tool_stats: Sequence[ToolUsageStats], error_events: Sequence[StructuredEvent]
    ) -> str:
        """Analyze failure mode (Root cause analysis)."""
        error_types = Counter(evt.event_type for evt in error_events)

        failure_reasons: Counter[str] = Counter()
        for stat in tool_stats:
            failure_reasons.update(stat.failure_reasons)

        if error_types["tool_timeout"] >= _TIMEOUT_MODE_MIN_EVENTS:
            return "timeout"
        if any("permission" in reason.lower() or "403" in reason for reason in failure_reasons):
            return "permission"
        if error_types["tool_failure"]:
            return "tool_error"
        return "unknown"

    def _cluster_similar_errors(self, error_events: Sequence[StructuredEvent]) -> dict[str, list[StructuredEvent]]:
        """Cluster similar errors to reduce redundancy."""
        clusters: dict[str, list[StructuredEvent]] = {}
        for evt in error_events:
            error_msg = str(evt.data.get("error") or evt.data.get("error_code") or "")

            for cluster_key, members in clusters.items():
                if SequenceMatcher(None, cluster_key, error_msg).ratio() > _CLUSTER_SIMILARITY:
                    members.append(evt)
                    break
            else:
                clusters[error_msg] = [evt]

        return clusters

    def _format_for_llm(self, evidence: _TraceEvidence, failure_mode: str, skill_id: str, max_tokens: int) -> str:
        """Format for LLM with progressive disclosure and token budget locking."""
        summary = evidence.summary
        tool_stats = evidence.tool_stats
        lines = [
            "## Session Overview",
            f"- Target skill: **{skill_id}**",
            f"- Duration: {summary.duration_ms / 1000:.1f}s",
            f"- Distinct tools used: {len(summary.tool_breakdown)}",
        ]
        if summary.token_economics:
            lines.append(f"- Tokens used: {summary.token_economics.get('total_tokens', 0)}")
        lines.append("")

        lines.append("## Failure Analysis")
        lines.append(f"**Failure mode**: `{failure_mode}`")
        guidance = _FAILURE_GUIDANCE.get(failure_mode)
        if guidance:
            lines.append(f"**Likely cause**: {guidance[0]}")
            lines.append(f"**Suggested fix**: {guidance[1]}")
        lines.append("")

        if tool_stats:
            lines.append("## Tool Stats")
            for stat in tool_stats[:_MAX_TOOL_STATS]:
                success_rate = stat.success_count / stat.total_calls if stat.total_calls > 0 else 0
                marker = " (Target)" if stat.tool_name == skill_id else ""
                lines.append(
                    f"- **{_stored_tool_name(stat.tool_name)}**{marker}: "
                    f"{stat.total_calls} calls, "
                    f"success rate {success_rate:.1%}, "
                    f"{stat.failure_count} failures"
                )
            lines.append("")

        if evidence.error_events:
            lines.append("## Error Details")
            clusters = self._cluster_similar_errors(evidence.error_events)

            for i, (error_msg, evts) in enumerate(list(clusters.items())[:_MAX_ERROR_CLUSTERS]):
                if len(error_msg) > _ERROR_MESSAGE_CHARS:
                    error_msg = error_msg[:_ERROR_MESSAGE_CHARS] + "...(truncated)"

                marker = " (Target)" if any(e.data.get("tool_name") == skill_id for e in evts) else ""
                lines.append(f"{i + 1}. [{evts[0].event_type}]{marker} (seen {len(evts)}x) {error_msg}")
            lines.append("")

        lines.append("## Run Totals")
        lines.append(f"- Tool events: {evidence.tool_event_count}")
        lines.append(f"- Latest errors listed: {len(evidence.error_events)}")
        if tool_stats:
            avg_success_rate = sum(
                s.success_count / s.total_calls if s.total_calls > 0 else 0 for s in tool_stats
            ) / len(tool_stats)
            lines.append(f"- Average success rate: {avg_success_rate:.1%}")

        if evidence.recent_events:
            lines.append("\n## Recent Tool Events")
            for evt in evidence.recent_events:
                marker = " (Target)" if evt.data.get("tool_name") == skill_id else ""
                lines.append(f"- {evt.event_type}: {_stored_tool_name(evt.data.get('tool_name', ''))}{marker}")

        output = "\n".join(lines)

        max_chars = max_tokens * _CHARS_PER_TOKEN
        if len(output) > max_chars:
            output = output[:max_chars] + "\n\n...(truncated to fit token budget)"

        return output
