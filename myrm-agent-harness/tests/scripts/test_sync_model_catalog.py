"""Unit tests for the model catalog sync: trimming, the union merge, the report and the refusal guard."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "sync_model_catalog",
    Path(__file__).resolve().parents[2] / "scripts/sync_model_catalog.py",
)
assert _spec and _spec.loader
_sync = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _sync  # dataclasses resolve their string annotations through the module registry
_spec.loader.exec_module(_sync)


def _entry(**fields: object) -> dict[str, object]:
    return {"provider": "vendor", "mode": "chat", **fields}


class TestTrim:
    def test_only_listed_modes_and_read_fields_survive_and_the_provider_is_renamed(self) -> None:
        trimmed = _sync.trim(
            {
                "sample_spec": {"mode": "chat"},
                "kept": {"litellm_provider": "vendor", "mode": "chat", "max_input_tokens": 8, "source": "https://x"},
                "audio": {"litellm_provider": "vendor", "mode": "audio_speech"},
                "not-a-model": "text",
            }
        )
        assert trimmed == {"kept": {"provider": "vendor", "mode": "chat", "max_input_tokens": 8}}

    def test_the_flags_that_shape_a_request_are_kept(self) -> None:
        flags = {
            "supports_sampling_params": False,
            "supports_adaptive_thinking": True,
            "supports_output_config": True,
            "supports_native_structured_output": True,
            "supports_parallel_tool_use_config": True,
            "supports_none_reasoning_effort": True,
            "supports_xhigh_reasoning_effort": True,
            "supports_max_reasoning_effort": False,
        }
        trimmed = _sync.trim({"m": {"litellm_provider": "vendor", "mode": "chat", **flags, "supports_unrelated": True}})
        assert trimmed == {"m": {"provider": "vendor", "mode": "chat", **flags}}

    def test_price_tiers_are_kept_with_only_the_range_and_the_rates_billed_inside_it(self) -> None:
        tiers = [
            {"range": [0, 32000.0], "input_cost_per_token": 1e-6, "output_cost_per_token": 6e-6, "note": "x"},
            {
                "range": [32000.0, 128000.0],
                "input_cost_per_token": 2e-6,
                "output_cost_per_token": 1e-5,
                "cache_read_input_token_cost": 4e-7,
            },
        ]
        trimmed = _sync.trim({"m": {"litellm_provider": "vendor", "mode": "chat", "tiered_pricing": tiers}})
        assert trimmed["m"]["tiered_pricing"] == [
            {"range": [0, 32000.0], "input_cost_per_token": 1e-6, "output_cost_per_token": 6e-6},
            tiers[1],
        ]

    def test_a_window_stated_as_a_whole_float_is_stored_as_the_integer_it_is(self) -> None:
        raw = {
            "litellm_provider": "vendor",
            "mode": "chat",
            "max_input_tokens": 131072.0,
            "max_output_tokens": 8192,
            "max_tokens": 4096.5,
            "output_vector_size": 1024.0,
            "input_cost_per_token": 2.0,
        }
        trimmed = _sync.trim({"m": raw})["m"]
        assert trimmed["max_input_tokens"] == 131072 and isinstance(trimmed["max_input_tokens"], int)
        assert trimmed["output_vector_size"] == 1024 and isinstance(trimmed["output_vector_size"], int)
        assert trimmed["max_output_tokens"] == 8192
        assert trimmed["max_tokens"] == 4096.5  # a fractional value is not a count to be rounded
        assert trimmed["input_cost_per_token"] == 2.0 and isinstance(trimmed["input_cost_per_token"], float)


class TestUnreadablePrices:
    @staticmethod
    def _families(raw: dict[str, object]) -> dict[str, int]:
        return _sync.unreadable_prices(raw, _sync.trim(raw))

    def test_a_chat_entry_priced_per_second_or_per_character_is_counted_under_its_provider(self) -> None:
        raw = {
            "a": {"litellm_provider": "bedrock", "mode": "chat", "input_cost_per_second": 0.1},
            "b": {"litellm_provider": "bedrock", "mode": "chat", "input_cost_per_character": 1e-6},
            "c": {"litellm_provider": "vertex", "mode": "responses", "cost_per_second": 0.2},
        }
        assert self._families(raw) == {"bedrock": 2, "vertex": 1}

    def test_flat_and_tiered_token_rates_and_priceless_or_non_chat_entries_are_not_counted(self) -> None:
        tier = {"range": [0, 8], "input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6}
        raw = {
            "flat": {
                "litellm_provider": "v",
                "mode": "chat",
                "input_cost_per_token": 1e-6,
                "output_cost_per_token": 2e-6,
            },
            "tiered": {"litellm_provider": "v", "mode": "chat", "tiered_pricing": [tier]},
            "free": {"litellm_provider": "v", "mode": "chat", "max_input_tokens": 8},
            "image": {"litellm_provider": "v", "mode": "image_generation", "output_cost_per_image": 0.04},
        }
        assert self._families(raw) == {}

    def test_a_price_shape_the_trimming_does_not_keep_is_what_the_count_exists_to_show(self) -> None:
        # Tiers whose rows state no input or no output rate leave the model unpriced: counted, not silently lost.
        raw = {
            "m": {
                "litellm_provider": "v",
                "mode": "chat",
                "tiered_pricing": [{"range": [0, 8], "input_cost_per_token": 1e-6}],
            }
        }
        assert self._families(raw) == {"v": 1}

    def test_the_report_gives_the_families_and_their_total(self) -> None:
        result = _sync.merge({}, {})
        assert "chat entries with a price but no token rate: 3 (bedrock 2, vertex 1)" in _sync._report(
            result, {"bedrock": 2, "vertex": 1}
        )
        assert "chat entries with a price but no token rate: 0 (none)" in _sync._report(result, {})


class TestMerge:
    def test_upstream_replaces_a_listed_entry_whole_so_a_corrected_flag_does_not_survive(self) -> None:
        snapshot = {"m": _entry(supports_reasoning=True, max_input_tokens=8)}
        upstream = {"m": _entry(max_input_tokens=16)}
        result = _sync.merge(snapshot, upstream)
        assert result.table["m"] == upstream["m"]
        assert result.updated == ["m"]

    def test_a_model_upstream_stopped_listing_keeps_its_last_entry(self) -> None:
        snapshot = {"gone": _entry(max_input_tokens=8), "kept": _entry(max_input_tokens=8)}
        result = _sync.merge(snapshot, {"kept": _entry(max_input_tokens=8)})
        assert result.table["gone"] == snapshot["gone"]
        assert result.retained == ["gone"]
        assert result.updated == []

    def test_a_new_model_is_added(self) -> None:
        result = _sync.merge({}, {"fresh": _entry(max_input_tokens=8)})
        assert result.added == ["fresh"] and "fresh" in result.table

    def test_a_window_or_price_upstream_stopped_stating_is_reported_for_review_not_patched(self) -> None:
        snapshot = {"m": _entry(max_input_tokens=8, input_cost_per_token=1e-6, supports_vision=True)}
        upstream = {"m": _entry(input_cost_per_token=1e-6)}
        result = _sync.merge(snapshot, upstream)
        assert result.lost_facts == [("m", "max_input_tokens")]
        assert "max_input_tokens" not in result.table["m"]

    def test_a_dropped_flag_is_not_a_lost_fact_and_a_retained_model_never_is(self) -> None:
        snapshot = {"m": _entry(supports_vision=True), "gone": _entry(max_input_tokens=8)}
        result = _sync.merge(snapshot, {"m": _entry()})
        assert result.lost_facts == []


class TestMain:
    @pytest.fixture()
    def snapshot_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        path = tmp_path / "model_catalog.json"
        path.write_text(
            json.dumps({"a": _entry(max_input_tokens=1), "b": _entry(max_input_tokens=2)}), encoding="utf-8"
        )
        monkeypatch.setattr(_sync, "OUTPUT", path)
        return path

    @staticmethod
    def _upstream(tmp_path: Path, table: dict[str, object]) -> list[str]:
        source = tmp_path / "upstream.json"
        source.write_text(json.dumps(table), encoding="utf-8")
        return ["--source", str(source)]

    def test_the_written_snapshot_is_the_union_and_the_report_counts_the_changes(
        self, snapshot_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        upstream = {"a": {"litellm_provider": "vendor", "mode": "chat", "max_input_tokens": 9}}
        monkeypatch.setattr("sys.argv", ["sync", *self._upstream(tmp_path, upstream)])
        assert _sync.main() == 0
        written = json.loads(snapshot_file.read_text(encoding="utf-8"))
        assert written["a"]["max_input_tokens"] == 9 and "b" in written
        report = capsys.readouterr().out
        assert "added 0, updated 1, kept although upstream dropped them 1" in report
        assert "chat entries with a price but no token rate: 0 (none)" in report

    def test_an_upstream_that_keeps_under_half_the_snapshot_is_refused_and_nothing_is_written(
        self, snapshot_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        before = snapshot_file.read_text(encoding="utf-8")
        upstream = {"z": {"litellm_provider": "vendor", "mode": "chat"}}
        monkeypatch.setattr("sys.argv", ["sync", *self._upstream(tmp_path, upstream)])
        assert _sync.main() == 1
        assert snapshot_file.read_text(encoding="utf-8") == before

    def test_the_first_sync_without_a_snapshot_writes_the_trimmed_upstream(
        self, snapshot_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        snapshot_file.unlink()
        upstream = {"z": {"litellm_provider": "vendor", "mode": "chat"}}
        monkeypatch.setattr("sys.argv", ["sync", *self._upstream(tmp_path, upstream)])
        assert _sync.main() == 0
        assert list(json.loads(snapshot_file.read_text(encoding="utf-8"))) == ["z"]
