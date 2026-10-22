"""Architecture test: every server stream consumer that builds answer text honours the restart contract.

A harness recovery (truncation retry, context-pressure handling, model switch) announces ``restart`` and then
streams the in-flight answer segment again. A consumer that concatenates ``message`` events itself repeats that
segment in what it delivers or persists. ``AnswerDraft`` (final answers) and ``StreamContentCollector``
(persisted turn content) are the two sanctioned accumulators, so each call site of ``process_stream`` /
``ai_agent_service_stream`` must be classified here: it uses one of them, delegates to a module that does, or
never assembles text.

Limit: this scans server call sites only. A harness-internal caller that drives a child agent through ``run()``
is not visible to it and is covered by its own unit test.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[2] / "app"
_STREAM_ENTRYPOINTS = ("process_stream", "ai_agent_service_stream")
_ACCUMULATORS = ("AnswerDraft", "StreamContentCollector")

# The file that makes the call also accumulates the answer.
_ACCUMULATES_HERE = {
    "api/openai_compat/completions.py",
    "core/channel_bridge/executor_helpers/approval.py",
    "core/cron/adapters/agent_runner.py",
    "lifecycle/auto_continue.py",
    "services/agent/streaming_support/hitl_timeout.py",
    "services/agent/wakeup_handler.py",
}
# The call site hands each event to a collaborator that accumulates the answer.
_DELEGATES = {
    "core/channel_bridge/agent_executor/executor.py": "core/channel_bridge/executor_helpers/stream.py",
    "core/eval/executor.py": "core/eval/stream_trace.py",
    "services/agent/stream_session/stream_loop.py": "services/agent/stream_session/stream_session_types.py",
    "services/kanban/task_runner/runner.py": "services/kanban/task_runner/stream.py",
}
# The call site never assembles answer text.
_NO_ANSWER_TEXT = {
    # Produces the event stream the other consumers read.
    "services/agent/streaming.py": "gateway entry point; yields events unchanged",
    # Speech is played as it arrives; audio already played cannot be retracted.
    "api/voice/agent_bridge.py": "spoken output is not retractable",
    "api/voice/realtime.py": "spoken output is not retractable",
    # Drains the stream to completion for its side effects and discards every event.
    "services/agent/goals/goal_stream_trigger.py": "events are discarded",
}


def _count_calls(source: str, names: tuple[str, ...]) -> int:
    return sum(
        1
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id in names)
            or (isinstance(node.func, ast.Attribute) and node.func.attr in names)
        )
    )


def _uses_accumulator(source: str) -> bool:
    """Whether the code (not a docstring, comment or import) names one of the accumulators."""
    return any(
        (isinstance(node, ast.Name) and node.id in _ACCUMULATORS)
        or (isinstance(node, ast.Attribute) and node.attr in _ACCUMULATORS)
        for node in ast.walk(ast.parse(source))
    )


@cache
def _call_sites() -> frozenset[str]:
    return frozenset(
        path.relative_to(_APP).as_posix()
        for path in _APP.rglob("*.py")
        if any(name in (text := path.read_text(encoding="utf-8")) for name in _STREAM_ENTRYPOINTS)
        and _count_calls(text, _STREAM_ENTRYPOINTS)
    )


def test_detector_counts_attribute_and_plain_calls() -> None:
    assert _count_calls("async for e in agent.process_stream(q): pass", _STREAM_ENTRYPOINTS) == 1
    assert _count_calls("async for e in ai_agent_service_stream(p): pass", _STREAM_ENTRYPOINTS) == 1
    assert _count_calls("def process_stream(self): ...  # ai_agent_service_stream(", _STREAM_ENTRYPOINTS) == 0


def test_accumulator_detector_ignores_imports_comments_and_docstrings() -> None:
    assert _uses_accumulator("draft = AnswerDraft()")
    assert _uses_accumulator("c: StreamContentCollector = field(default_factory=StreamContentCollector)")
    assert _uses_accumulator("x = mod.AnswerDraft()")
    unused = 'from m import AnswerDraft\n# AnswerDraft\ndef f():\n    """AnswerDraft"""\n'
    assert not _uses_accumulator(unused)


def test_the_scan_sees_the_known_call_sites() -> None:
    assert len(_call_sites()) >= 10, "the source scan found fewer call sites than exist; the guard is blind"


@pytest.mark.architecture
def test_every_stream_call_site_is_classified() -> None:
    classified = _ACCUMULATES_HERE | set(_DELEGATES) | set(_NO_ANSWER_TEXT)

    assert _call_sites() == classified, (
        "stream call sites changed. A consumer that builds answer text must accumulate it with AnswerDraft "
        "(final answers) or StreamContentCollector (persisted turns) so a recovery restart replaces the "
        "in-flight segment; classify the new call site in _ACCUMULATES_HERE, _DELEGATES or _NO_ANSWER_TEXT."
    )


@pytest.mark.architecture
@pytest.mark.parametrize("relative_path", sorted(_ACCUMULATES_HERE))
def test_call_site_accumulates_with_a_restart_aware_class(relative_path: str) -> None:
    source = (_APP / relative_path).read_text(encoding="utf-8")

    assert _uses_accumulator(source), f"{relative_path} builds answer text without AnswerDraft or StreamContentCollector"


@pytest.mark.architecture
@pytest.mark.parametrize(("relative_path", "delegate"), sorted(_DELEGATES.items()))
def test_delegate_accumulates_with_a_restart_aware_class(relative_path: str, delegate: str) -> None:
    assert delegate.rsplit("/", 1)[-1].removesuffix(".py") in (_APP / relative_path).read_text(encoding="utf-8"), (
        f"{relative_path} no longer hands its events to {delegate}"
    )
    source = (_APP / delegate).read_text(encoding="utf-8")

    assert _uses_accumulator(source), f"{delegate} builds answer text without AnswerDraft or StreamContentCollector"
