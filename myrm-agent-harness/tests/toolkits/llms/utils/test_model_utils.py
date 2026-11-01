"""Tests for llms/utils/model_utils — model introspection utilities."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.llms.catalog import register_model, store
from myrm_agent_harness.toolkits.llms.utils import model_utils
from myrm_agent_harness.toolkits.llms.utils.model_utils import (
    clamp_budget_to_model_ceiling,
    get_model_context_limit,
    get_model_output_ceiling,
)


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registrations a test makes never outlive it."""
    monkeypatch.setattr(store, "_REGISTERED", {})


class TestGetModelContextLimit:
    def test_n_ctx_attribute(self) -> None:
        llm = MagicMock()
        llm.n_ctx = 4096
        assert get_model_context_limit(llm) == 4096

    def test_model_max_context_length(self) -> None:
        llm = MagicMock(spec=[])
        llm.model_max_context_length = 8192
        assert get_model_context_limit(llm) == 8192

    def test_max_input_tokens(self) -> None:
        llm = MagicMock(spec=[])
        llm.max_input_tokens = 128000
        assert get_model_context_limit(llm) == 128000

    def test_returns_none_when_no_attr(self) -> None:
        llm = MagicMock(spec=[])
        llm.model_name = ""
        llm.model = ""
        result = get_model_context_limit(llm)
        assert result is None

    def test_catalog_fallback(self) -> None:
        register_model("vendor/windowed-model", {"max_input_tokens": 128000})
        llm = MagicMock(spec=[])
        llm.model_name = "vendor/windowed-model"
        llm.model = "vendor/windowed-model"
        assert get_model_context_limit(llm) == 128000

    def test_unknown_model_returns_none(self) -> None:
        llm = MagicMock(spec=[])
        llm.model_name = "vendor/unlisted-model"
        llm.model = "vendor/unlisted-model"
        assert get_model_context_limit(llm) is None

    def test_zero_value_skipped(self) -> None:
        llm = MagicMock(spec=[])
        llm.n_ctx = 0
        llm.model_max_context_length = 0
        llm.max_input_tokens = 0
        llm.model_name = ""
        llm.model = ""
        assert get_model_context_limit(llm) is None

    def test_negative_value_skipped(self) -> None:
        llm = MagicMock(spec=[])
        llm.n_ctx = -1
        llm.model_max_context_length = -100
        llm.max_input_tokens = 4096
        assert get_model_context_limit(llm) == 4096

    def test_extra_body_options_num_ctx(self) -> None:
        llm = MagicMock(spec=[])
        llm.extra_body = {"options": {"num_ctx": 64000}}
        assert get_model_context_limit(llm) == 64000

    def test_extra_body_options_invalid_type_graceful(self) -> None:
        llm = MagicMock(spec=[])
        llm.extra_body = {"options": "invalid"}
        llm.model_max_context_length = 8192
        assert get_model_context_limit(llm) == 8192

    def test_extra_body_options_zero_num_ctx_ignored(self) -> None:
        llm = MagicMock(spec=[])
        llm.extra_body = {"options": {"num_ctx": 0}}
        llm.max_input_tokens = 16384
        assert get_model_context_limit(llm) == 16384


class TestGetModelOutputCeiling:
    def test_reads_max_output_tokens_not_the_legacy_max_tokens_field(self) -> None:
        """For part of the table ``max_tokens`` holds the context window, which is not an output limit."""
        register_model("vendor/ceiling-model", {"max_tokens": 200_000, "max_output_tokens": 64_000})
        assert get_model_output_ceiling("vendor/ceiling-model") == 64_000

    def test_unmapped_model_has_no_ceiling(self) -> None:
        assert get_model_output_ceiling("vendor/unmapped-model") is None

    @pytest.mark.parametrize("table_value", [None, 0, -5, "64000", True])
    def test_unusable_table_value_is_ignored(self, table_value: object) -> None:
        register_model("vendor/odd-table-entry", {"max_output_tokens": table_value})
        assert get_model_output_ceiling("vendor/odd-table-entry") is None

    def test_empty_name_skips_the_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _unexpected(_model: str) -> None:
            raise AssertionError("the table must not be consulted for an empty model name")

        monkeypatch.setattr(model_utils, "model_info", _unexpected)
        assert get_model_output_ceiling("") is None


class TestClampBudgetToModelCeiling:
    @staticmethod
    def _pin_ceiling(monkeypatch: pytest.MonkeyPatch, ceiling: int | None) -> None:
        monkeypatch.setattr(model_utils, "get_model_output_ceiling", lambda _model: ceiling)

    def test_unknown_ceiling_leaves_the_request_untouched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._pin_ceiling(monkeypatch, None)
        assert clamp_budget_to_model_ceiling("m", 65_536, accepted=4096) == 65_536

    def test_request_above_the_ceiling_is_limited_to_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._pin_ceiling(monkeypatch, 64_000)
        assert clamp_budget_to_model_ceiling("m", 65_536, accepted=4096) == 64_000

    def test_request_within_the_ceiling_is_untouched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._pin_ceiling(monkeypatch, 128_000)
        assert clamp_budget_to_model_ceiling("m", 65_536, accepted=4096) == 65_536

    def test_ceiling_below_an_accepted_budget_is_treated_as_stale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A budget the provider already served proves the table entry outdated; it is never undercut."""
        self._pin_ceiling(monkeypatch, 8192)
        assert clamp_budget_to_model_ceiling("m", 32_768, accepted=16_384) == 16_384
