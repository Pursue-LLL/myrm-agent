"""Golden failures test: every recorded failure is classified as the previous stack classified it, except where registered.

[INPUT]
- golden_failures (POS: replays the recorded failures through the chat adapter on the installed stack)
- golden_failures_baseline.json (POS: the failures and the verdicts the previous stack reached on them)
- golden_failures_allowed (POS: registry of intended differences)
- golden_compare (POS: comparison engine)

[OUTPUT]
- tests that fail on any unregistered difference, on a registered difference whose facts changed, and on a registry
  entry that matches nothing

[POS]
Safety net for the agent's recovery. 132 error replies (status, headers, body of OpenAI, Azure, Anthropic, Gemini and
Ollama endpoints and the vendors behind them) and 36 streams (an error event first or after text, an empty or garbage
body, a connection cut off on the way) must lead to the same failover reason, error kind, overflow and quota verdicts,
and the same wait the provider asked for, as before the stack was replaced.
"""

from __future__ import annotations

import pytest

from .golden_compare import Report, compare
from .golden_failures import FailureBaseline, load_baseline, replay_http, replay_streams
from .golden_failures_allowed import HTTP_ALLOWED, STREAM_ALLOWED


@pytest.fixture(scope="module")
def baseline() -> FailureBaseline:
    return load_baseline()


@pytest.fixture(scope="module")
def http_report(baseline: FailureBaseline) -> Report:
    recorded = {name: case["old"] for name, case in baseline["http"].items()}
    return compare(recorded, replay_http(baseline["http"]), HTTP_ALLOWED)


@pytest.fixture(scope="module")
def stream_report(baseline: FailureBaseline) -> Report:
    recorded = {name: case["old"] for name, case in baseline["stream"].items()}
    return compare(recorded, replay_streams(baseline["stream"]), STREAM_ALLOWED)


def test_the_recording_keeps_every_case(baseline: FailureBaseline) -> None:
    """A case cannot leave the contract unnoticed: removing one from the file changes these counts."""
    assert (len(baseline["http"]), len(baseline["stream"])) == (132, 36)


def test_every_error_reply_is_classified_as_before_or_registered(http_report: Report) -> None:
    assert not http_report.unexplained, f"{len(http_report.unexplained)} replies:\n{http_report.describe()}"


def test_the_http_registry_has_no_stale_entries(http_report: Report) -> None:
    assert not http_report.stale, f"registered differences that no longer occur: {http_report.stale}"


def test_every_stream_failure_is_classified_as_before_or_registered(stream_report: Report) -> None:
    assert not stream_report.unexplained, f"{len(stream_report.unexplained)} streams:\n{stream_report.describe()}"


def test_the_stream_registry_has_no_stale_entries(stream_report: Report) -> None:
    assert not stream_report.stale, f"registered differences that no longer occur: {stream_report.stale}"
