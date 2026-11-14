"""Tests for how the gateway normalizer treats a rejected reasoning control.

A gateway that answers 400 to ``reasoning_effort`` or ``thinking`` must be retried without exactly that control, from
the top level and from ``extra_body`` alike, and the endpoint must not be asked the same thing again.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from myrm_agent_harness.toolkits.llms.adapters import gateway_normalizer as gn
from myrm_agent_harness.toolkits.llms.adapters.gateway_normalizer import (
    drop_rejected_reasoning_params,
    is_gateway_param_rejection,
    sanitize_gateway_params_on_400,
)

_MODEL = "openai/deepseek-v4.1-flash"
_BASE = "https://gateway.example/v1"


@pytest.fixture(autouse=True)
def _isolated_reasoning_memo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gn, "_REJECTED_REASONING", {})


def _effort_params(level: str = "max") -> dict[str, object]:
    """The request shape the model factory builds: the effort at the top level and mirrored into extra_body."""
    return {"reasoning_effort": level, "extra_body": {"reasoning_effort": level, "keep": True}}


class TestThinkingRejectionWording:
    @pytest.mark.parametrize(
        "message",
        [
            "Unrecognized request argument supplied: thinking",
            "unknown parameter: thinking",
            "Unsupported parameter(s): thinking",
            "the thinking field is not supported by this model",
            "[{'type': 'extra_forbidden', 'loc': ('body', 'thinking'), 'msg': 'Extra inputs are not permitted'}]",
        ],
    )
    def test_names_of_the_rejection_are_recognised(self, message: str) -> None:
        params: dict[str, object] = {"thinking": {"type": "disabled"}, "extra_body": {"thinking": {"type": "disabled"}}}

        assert is_gateway_param_rejection(Exception(message)) is True
        assert sanitize_gateway_params_on_400(params, Exception(message), model=_MODEL, base_url=_BASE) == ["thinking"]
        assert "thinking" not in params
        assert params["extra_body"] == {}

    def test_unrelated_message_mentioning_thinking_is_not_a_rejection(self) -> None:
        message = "maximum context length is exceeded; thinking tokens count toward it"

        assert is_gateway_param_rejection(Exception(message)) is False


class TestRejectedParamLeavesEveryLevel:
    def test_top_level_and_extra_body_mirror_are_both_stripped(self) -> None:
        params = _effort_params()

        stripped = sanitize_gateway_params_on_400(
            params, Exception("Unrecognized request argument supplied: reasoning_effort"), model=_MODEL, base_url=_BASE
        )

        assert stripped == ["reasoning_effort"]
        assert "reasoning_effort" not in params
        assert params["extra_body"] == {"keep": True}

    def test_shared_extra_body_dict_is_not_mutated(self) -> None:
        """The mirror is the model configuration's own dict: the retry must not edit it in place."""
        shared = {"reasoning_effort": "max", "keep": True}
        params: dict[str, object] = {"extra_body": shared}

        sanitize_gateway_params_on_400(
            params, Exception("unknown field reasoning_effort"), model=_MODEL, base_url=_BASE
        )

        assert shared == {"reasoning_effort": "max", "keep": True}
        assert params["extra_body"] == {"keep": True}

    def test_param_held_only_in_extra_body_is_stripped(self) -> None:
        params: dict[str, object] = {"extra_body": {"reasoning_effort": "low"}}

        stripped = sanitize_gateway_params_on_400(
            params, Exception("unsupported reasoning_effort"), model=_MODEL, base_url=_BASE
        )

        assert stripped == ["reasoning_effort"]
        assert params["extra_body"] == {}

    def test_absent_param_is_not_reported_as_stripped(self) -> None:
        params: dict[str, object] = {"temperature": 0.2}

        assert sanitize_gateway_params_on_400(params, Exception("unsupported reasoning_effort")) == []


class TestRejectedReasoningMemory:
    def test_a_rejected_level_is_dropped_from_the_next_request(self) -> None:
        sanitize_gateway_params_on_400(
            _effort_params("max"), Exception("unsupported reasoning_effort"), model=_MODEL, base_url=_BASE
        )

        next_request = _effort_params("max")
        drop_rejected_reasoning_params(next_request, model=_MODEL, base_url=_BASE)

        assert "reasoning_effort" not in next_request
        assert next_request["extra_body"] == {"keep": True}

    def test_a_level_the_endpoint_never_rejected_is_kept(self) -> None:
        sanitize_gateway_params_on_400(
            _effort_params("max"), Exception("unsupported reasoning_effort"), model=_MODEL, base_url=_BASE
        )

        other_level = _effort_params("high")
        drop_rejected_reasoning_params(other_level, model=_MODEL, base_url=_BASE)

        assert other_level == _effort_params("high")

    def test_another_endpoint_or_model_is_unaffected(self) -> None:
        sanitize_gateway_params_on_400(
            _effort_params("max"), Exception("unsupported reasoning_effort"), model=_MODEL, base_url=_BASE
        )

        elsewhere = _effort_params("max")
        drop_rejected_reasoning_params(elsewhere, model=_MODEL, base_url="https://other.example/v1")
        other_model = _effort_params("max")
        drop_rejected_reasoning_params(other_model, model="openai/other-model", base_url=_BASE)

        assert elsewhere == other_model == _effort_params("max")

    def test_thinking_switch_is_remembered_by_value(self) -> None:
        disabled: dict[str, object] = {"extra_body": {"thinking": {"type": "disabled"}}}
        sanitize_gateway_params_on_400(disabled, Exception("unsupported thinking"), model=_MODEL, base_url=_BASE)

        again: dict[str, object] = {"extra_body": {"thinking": {"type": "disabled"}}}
        drop_rejected_reasoning_params(again, model=_MODEL, base_url=_BASE)
        enabled: dict[str, object] = {"extra_body": {"thinking": {"type": "enabled"}}}
        drop_rejected_reasoning_params(enabled, model=_MODEL, base_url=_BASE)

        assert again["extra_body"] == {}
        assert enabled["extra_body"] == {"thinking": {"type": "enabled"}}

    def test_memory_expires(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sanitize_gateway_params_on_400(
            _effort_params("max"), Exception("unsupported reasoning_effort"), model=_MODEL, base_url=_BASE
        )

        later = gn.time.monotonic() + gn._REJECTED_REASONING_TTL_S + 1
        monkeypatch.setattr(gn, "time", SimpleNamespace(monotonic=lambda: later))
        request = _effort_params("max")
        drop_rejected_reasoning_params(request, model=_MODEL, base_url=_BASE)

        assert request == _effort_params("max")
        assert gn._REJECTED_REASONING == {}

    def test_other_rejected_params_are_not_remembered(self) -> None:
        sanitize_gateway_params_on_400(
            {"temperature": 0.2}, Exception("temperature is not supported"), model=_MODEL, base_url=_BASE
        )

        assert gn._REJECTED_REASONING == {}

    def test_memory_is_bounded(self) -> None:
        for index in range(gn._MEMO_CAP + 10):
            sanitize_gateway_params_on_400(
                _effort_params("max"),
                Exception("unsupported reasoning_effort"),
                model=f"openai/model-{index}",
                base_url=_BASE,
            )

        assert len(gn._REJECTED_REASONING) == gn._MEMO_CAP

    def test_empty_memory_leaves_the_request_untouched(self) -> None:
        request = _effort_params("max")

        drop_rejected_reasoning_params(request, model=_MODEL, base_url=_BASE)

        assert request == _effort_params("max")
