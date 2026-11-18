"""Tests for parse_output_limit: rejections that are not output limits must read as None.

Each message is a neighbouring rejection (prompt overflow, rate limits, another parameter's range, a limit
worded without a usable number) that must never be read as an output limit: acting on one would shrink
max_tokens for a request that max_tokens did not break. The wordings that are output limits are in
test_output_limit.py.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.errors.output_limit import OutputLimit, parse_output_limit


def _limit(message: str) -> OutputLimit | None:
    return parse_output_limit(Exception(message))


class TestEdgeCases:
    def test_keywords_present_but_no_parseable_number(self) -> None:
        assert _limit("max_tokens exceeds available_tokens for this model") is None

    def test_equals_at_end_without_available_tokens_keyword(self) -> None:
        message = "max_tokens: 8192 > context_window: 128000 - input_tokens: 126000 = 2000"
        assert _limit(message) is None

    def test_available_tokens_zero(self) -> None:
        message = "max_tokens: 8192 > context_window: 128000 - input_tokens: 128000 = available_tokens: 0"
        assert _limit(message) is None


NOT_AN_OUTPUT_LIMIT = [
    pytest.param("prompt is too long: 205000 tokens > 200000 maximum", id="prompt-too-long"),
    pytest.param("some unrelated 400 error", id="generic-400"),
    pytest.param("rate limit exceeded: too many requests per minute", id="rate-limit"),
    pytest.param("Rate limit reached for gpt-4o: Limit 30000 tokens per min. Please try again in 6s.", id="tpm-limit"),
    pytest.param("invalid api key provided", id="auth"),
    pytest.param("context_length_exceeded: 205000 > 200000", id="context-overflow-without-numbers"),
    pytest.param("", id="empty"),
    pytest.param(
        "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.",
        id="o-series-unsupported-parameter",
    ),
    pytest.param(
        "A maximum of 4 blocks with cache_control may be provided. Found 5.",
        id="cache-control-blocks",
    ),
    pytest.param(
        "This prompt is longer than the free tier allows for a single request.",
        id="free-tier-prompt",
    ),
    pytest.param(
        "This model's maximum context length is 8192 tokens. However, your messages resulted in 9000 tokens. "
        "Please reduce the length of the messages.",
        id="prompt-alone-overflows",
    ),
    pytest.param(
        "Invalid 'n': integer above maximum value. Expected a value <= 1, but got 5 instead.",
        id="other-parameter-above-maximum",
    ),
    pytest.param("temperature must be less than or equal to 2", id="other-parameter-less-than-or-equal"),
    pytest.param("temperature: Must be less than or equal to 2", id="other-parameter-colon-less-than-or-equal"),
    pytest.param(
        '400 {"code":20015,"message":"length of prompt_tokens (51353) must be less than max_seq_len (32768).",'
        '"data":null}',
        id="siliconflow-prompt-overflow-shares-the-code-20015",
    ),
    pytest.param(
        "Unable to submit request because it has a temperature value of 3 but the supported range is from 0 "
        "(inclusive) to 2 (exclusive). Update the value and try again.",
        id="gemini-other-parameter-range",
    ),
    pytest.param(
        "Invalid 'max_tokens': integer below minimum value. Expected a value >= 1, but got 0 instead.",
        id="max-tokens-below-minimum",
    ),
    pytest.param(
        "too many tokens: size limit exceeded by 168512 tokens. Try using shorter or fewer inputs. "
        "The limit for this model is 132000 tokens.",
        id="cohere-prompt-overflow",
    ),
    pytest.param("max input tokens must be less than or equal to 8000", id="space-separated-prompt-limit"),
    pytest.param("max tokens allowed per minute must be less than or equal to 8000", id="space-separated-other-limit"),
    pytest.param(
        "Input validation error: `inputs` must have less than 4096 tokens. Given: 5000",
        id="tgi-prompt-only-length",
    ),
]


class TestNotAnOutputLimit:
    @pytest.mark.parametrize("message", NOT_AN_OUTPUT_LIMIT)
    def test_neighbouring_rejections_are_ignored(self, message: str) -> None:
        assert _limit(message) is None
