"""Which provider answers the live e2e tests treat as a broken environment (skip) and which as a real agent error (fail).

The live tests run against whatever account a developer put in ``.env.test``. A wrong model name, an expired key or a
quota that ran out is the developer's environment, not an agent bug, so ``check_e2e_errors`` skips on it.
"""

from __future__ import annotations

import pytest

from tests.api.agent.utils import check_e2e_errors


def _error_event(message: str) -> list[dict[str, object]]:
    return [{"type": "token", "data": "hi"}, {"type": "error", "error": message}]


class TestTopLevelErrorEvent:
    @pytest.mark.parametrize(
        "message",
        [
            'openai API error 401: {"error": {"message": "Incorrect API key provided"}}',
            'openai API error 429: {"error": {"message": "rate limit reached"}}',
            'openai API error 503: {"error": {"message": "overloaded"}}',
            # A provider that refuses the configured model: the model name in .env.test is wrong.
            'openai API error 400: {"error": {"message": "invalid params, unknown model \'typo\' (2013)"}}',
            # A model id that names no provider and has no api_base: the .env.test entry is incomplete.
            "Cannot resolve a provider for model 'typo': use a 'provider/model' id or set an api_base",
        ],
    )
    def test_an_environment_problem_skips_the_test(self, message: str) -> None:
        with pytest.raises(pytest.skip.Exception):
            check_e2e_errors(_error_event(message))

    @pytest.mark.parametrize(
        "message",
        [
            "KeyError: 'session'",
            'openai API error 404: {"error": {"message": "no such route"}}',
            "Agent stream ended without an answer",
        ],
    )
    def test_anything_else_is_a_real_agent_error(self, message: str) -> None:
        with pytest.raises(pytest.fail.Exception):
            check_e2e_errors(_error_event(message))


class TestFailuresInsideOtherEvents:
    def test_a_quota_failure_inside_a_tool_result_skips_the_test(self) -> None:
        events = [{"type": "tool_result", "data": "search service quota exhausted"}]
        with pytest.raises(pytest.skip.Exception):
            check_e2e_errors(events)

    def test_a_400_inside_a_tool_result_does_not_skip_the_test(self) -> None:
        # The tool's own request may be what the provider refused; only the top-level error event is a model setting.
        events = [{"type": "tool_result", "data": "web_fetch failed: HTTP API error 400 from the page"}]
        check_e2e_errors(events)

    def test_a_clean_stream_passes(self) -> None:
        check_e2e_errors([{"type": "token", "data": "hello"}, {"type": "done"}])
