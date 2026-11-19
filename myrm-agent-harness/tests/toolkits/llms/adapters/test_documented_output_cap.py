"""Tests for the ``max_tokens`` range a gateway documents for a model, applied before the first request.

The range is narrower than the model's own ceiling, and the thinking-headroom floor can ask for more than it, so a
request would otherwise be rejected on its first attempt.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from myrm_agent_harness.toolkits.llms.adapters.chat_model import TransportChatModel, output_cap_recovery
from myrm_agent_harness.toolkits.llms.adapters.chat_model.output_cap_recovery import apply_documented_output_cap
from myrm_agent_harness.toolkits.llms.ephemeral_output_tokens import (
    reset_ephemeral_max_output_tokens,
    set_ephemeral_max_output_tokens,
)

_NVIDIA = "https://integrate.api.nvidia.com/v1"
_MODEL = "openai/deepseek-ai/deepseek-v4-flash"


@pytest.fixture(autouse=True)
def _isolated_state() -> Iterator[None]:
    saved = dict(output_cap_recovery._LEARNED_CEILINGS)
    output_cap_recovery._LEARNED_CEILINGS.clear()
    reset_ephemeral_max_output_tokens()
    yield
    output_cap_recovery._LEARNED_CEILINGS.clear()
    output_cap_recovery._LEARNED_CEILINGS.update(saved)
    reset_ephemeral_max_output_tokens()


class TestApplyDocumentedOutputCap:
    @pytest.mark.parametrize("requested", [16_385, 32_768, 65_536])
    def test_a_larger_budget_is_lowered_to_the_documented_range(self, requested: int) -> None:
        params: dict[str, object] = {"max_tokens": requested, "keep": True}

        apply_documented_output_cap(params, model=_MODEL, base_url=_NVIDIA)

        assert params == {"max_tokens": 16_384, "keep": True}

    @pytest.mark.parametrize("requested", [1, 4_096, 16_384])
    def test_a_budget_inside_the_range_is_never_raised(self, requested: int) -> None:
        params: dict[str, object] = {"max_tokens": requested}

        apply_documented_output_cap(params, model=_MODEL, base_url=_NVIDIA)

        assert params == {"max_tokens": requested}

    def test_a_request_without_a_budget_gets_none_invented(self) -> None:
        params: dict[str, object] = {}

        apply_documented_output_cap(params, model=_MODEL, base_url=_NVIDIA)

        assert params == {}

    @pytest.mark.parametrize(
        ("model", "base_url"),
        [
            ("openai/meta/llama-3.3-70b-instruct", _NVIDIA),
            ("openai/deepseek-ai/DeepSeek-V4-Flash", "https://api.siliconflow.cn/v1"),
            (_MODEL, "https://gateway.example/v1"),
            (_MODEL, ""),
        ],
    )
    def test_no_other_endpoint_or_model_is_capped(self, model: str, base_url: str) -> None:
        params: dict[str, object] = {"max_tokens": 65_536}

        apply_documented_output_cap(params, model=model, base_url=base_url)

        assert params == {"max_tokens": 65_536}


class TestOutputBudgetOfAModel:
    def _model(self, **kwargs: object) -> TransportChatModel:
        return TransportChatModel(model=_MODEL, api_base=_NVIDIA, **kwargs)

    def test_a_truncation_boost_still_fits_the_documented_range(self) -> None:
        params: dict[str, object] = {"max_tokens": 16_384}
        set_ephemeral_max_output_tokens(65_536)

        self._model(max_tokens=16_384)._apply_output_budget(params)

        assert params["max_tokens"] == 16_384

    def test_a_tighter_learned_ceiling_still_applies(self) -> None:
        output_cap_recovery._remember_ceiling(_MODEL, _NVIDIA, 8_192)
        params: dict[str, object] = {"max_tokens": 65_536}

        self._model(max_tokens=65_536)._apply_output_budget(params)

        assert params["max_tokens"] == 8_192
