"""The failure report a repair prompt carries is built from the end of a chat's log, in English, from redacted text.

These tests run on a real ``FileEventLogBackend``: the limits that matter (a chat log holds every turn of the chat, and
the backend returns the first events of a limited read) only show with a log that is actually longer than the limit.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.event_log import sanitize_event_data
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.types import EventPayload, StructuredEvent
from myrm_agent_harness.agent.skills.evolution.core.engine import SkillEvolutionEngine
from myrm_agent_harness.agent.skills.evolution.core.types import SkillRecord
from myrm_agent_harness.agent.skills.evolution.pipeline import trace_analyzer as trace_analyzer_module
from myrm_agent_harness.agent.skills.evolution.pipeline.trace_analyzer import TraceAnalyzer

_SESSION_ID = "chat-with-a-long-log"
_NON_ENGLISH = re.compile(r"[\u3000-\u9fff\uff00-\uffef]")


def _event(sequence: int, event_type: str, **data: object) -> StructuredEvent:
    return StructuredEvent(
        sequence=sequence,
        timestamp=1_000.0 + sequence,
        event_type=event_type,
        session_id=_SESSION_ID,
        data=EventPayload(**data),
    )


async def _write(tmp_path: Path, events: list[StructuredEvent]) -> FileEventLogBackend:
    backend = FileEventLogBackend(tmp_path, _SESSION_ID)
    await backend.append(events)
    return backend


def _section(report: str, heading: str) -> str:
    """The text of ``heading`` up to the next heading."""
    return report.split(heading, 1)[1].split("\n## ", 1)[0]


@pytest.mark.asyncio
async def test_the_recent_tool_events_are_the_last_of_a_log_longer_than_the_read_limit(tmp_path: Path) -> None:
    calls = 6_000
    events: list[StructuredEvent] = []
    for call in range(calls):
        tool = "late_tool" if call >= calls - 3 else "early_tool"
        events.append(_event(2 * call + 1, "tool_start", tool_name=tool))
        events.append(_event(2 * call + 2, "tool_end", tool_name=tool))
    analyzer = TraceAnalyzer(await _write(tmp_path, events))

    report = await analyzer.extract_trajectory(_SESSION_ID, "late_tool")

    recent = _section(report, "## Recent Tool Events")
    assert "late_tool" in recent
    assert "early_tool" not in recent
    assert f"- Tool events: {2 * calls}" in report


@pytest.mark.asyncio
async def test_only_the_events_the_report_shows_are_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    failures = 3_000
    events = [_event(1, "tool_start", tool_name="bash")]
    events += [
        _event(index + 2, "tool_failure", tool_name="bash", error=f"deploy failed attempt {index:05d}")
        for index in range(failures)
    ]
    analyzer = TraceAnalyzer(await _write(tmp_path, events))
    redacted: list[int] = []

    def counting_sanitize(data: dict[str, object]) -> dict[str, object]:
        redacted.append(1)
        return sanitize_event_data(data)

    monkeypatch.setattr(trace_analyzer_module, "sanitize_event_data", counting_sanitize)

    report = await analyzer.extract_trajectory(_SESSION_ID, "bash")

    assert len(redacted) <= 40
    assert "attempt 02980" in report
    assert "(seen 20x)" in report


@pytest.mark.asyncio
async def test_the_report_is_english_and_names_no_session(tmp_path: Path) -> None:
    events = [
        _event(1, "tool_start", tool_name="bash"),
        _event(2, "tool_timeout", tool_name="bash", error="timed out"),
        _event(
            3,
            "takeover_trace",
            reason="user stuck",
            pre_url="https://example.com/a",
            post_url="https://example.com/a",
            duration_s=4.0,
            post_aria_tree="main",
        ),
    ]
    analyzer = TraceAnalyzer(await _write(tmp_path, events))

    report = await analyzer.extract_trajectory(_SESSION_ID, "bash")

    assert _NON_ENGLISH.search(report) is None
    assert _SESSION_ID not in report
    assert "## Human Takeover Evidence" in report
    assert "user stuck" in report


@pytest.mark.asyncio
async def test_a_log_with_no_events_for_the_chat_gives_no_report(tmp_path: Path) -> None:
    analyzer = TraceAnalyzer(await _write(tmp_path, [_event(1, "tool_start", tool_name="bash")]))

    assert await analyzer.extract_trajectory("another-chat", "bash") == ""


@pytest.mark.asyncio
async def test_the_repair_trajectory_holds_the_run_and_not_the_skill_text(tmp_path: Path) -> None:
    """The generator and the judge receive the skill on its own; repeating it in the trajectory only costs tokens."""
    skill_text = "UNIQUE-SKILL-BODY-LINE"
    backend = await _write(
        tmp_path,
        [
            _event(1, "tool_start", tool_name="bash"),
            _event(2, "tool_failure", tool_name="bash", error="exit 1"),
        ],
    )
    skill = SkillRecord(
        skill_id="deploy-001",
        name="deploy",
        description="Deploys the service.",
        content=f"# Deploy\n{skill_text}\n",
        path="/skills/deploy/SKILL.md",
        lineage=None,
    )
    store = MagicMock()
    store.get_skill.return_value = skill
    store.get_evolution_constraints.return_value = []
    engine = SkillEvolutionEngine(store=store, llm=MagicMock(), event_log_backend=backend)
    trajectories: list[str] = []

    async def no_variants(**kwargs: str) -> list[str]:
        trajectories.append(kwargs["trajectory"])
        return []

    engine._variant_generator.generate_variants = no_variants  # type: ignore[method-assign,assignment]

    await engine.fix_skill("deploy-001", "exit 1", session_id=_SESSION_ID)

    (trajectory,) = trajectories
    assert "exit 1" in trajectory
    assert skill_text not in trajectory


@pytest.mark.asyncio
async def test_a_call_written_whole_into_the_tool_name_does_not_push_the_failure_out_of_the_report(
    tmp_path: Path,
) -> None:
    badly_formed_call = 'write_file(path="/tmp/a.txt", content="' + "x" * 1_500 + '")'
    events: list[StructuredEvent] = []
    for index in range(5):
        events.append(_event(2 * index + 1, "tool_start", tool_name=f"{badly_formed_call}{index}"))
        events.append(_event(2 * index + 2, "tool_end", tool_name=f"{badly_formed_call}{index}"))
    events.append(_event(11, "tool_start", tool_name="skill_runner"))
    events.append(_event(12, "tool_failure", tool_name="skill_runner", error="connection refused by the upstream host"))
    analyzer = TraceAnalyzer(await _write(tmp_path, events))

    report = await analyzer.extract_trajectory(_SESSION_ID, "skill_runner")

    assert "connection refused by the upstream host" in _section(report, "## Error Details")
    assert "## Run Totals" in report
    assert "x" * 200 not in report
    assert "truncated to fit token budget" not in report
