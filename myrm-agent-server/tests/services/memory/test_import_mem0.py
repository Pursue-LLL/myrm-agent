"""Unit tests for the Mem0 memory import adapter.

Covers the `memories` / `results` dual-key payload shapes, semantic mapping
(fields, tags, importance, metadata, timestamps), empty/invalid item dropping,
auto-detection through the shared dispatcher, and an end-to-end dry-run
roundtrip through the import session entrypoint.
"""

from __future__ import annotations

import pytest

from app.services.memory.imports.import_adapters import build_memory_import_dry_run
from app.services.memory.imports.import_mem0 import dry_run_mem0, is_mem0_payload


def _mem0_payload(*, key: str = "memories", **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "_source": "mem0",
        key: [
            {
                "id": "mem-1",
                "memory": "Loves hiking on weekends",
                "metadata": {"importance": 0.8, "tags": ["hobby", "outdoor"]},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
            },
            {
                "id": "mem-2",
                "memory": "Prefers dark mode",
                "metadata": {"importance": 0.3},
            },
        ],
    }
    payload.update(overrides)
    return payload


class TestMem0PayloadDetection:
    def test_detects_via_source_tag(self) -> None:
        assert is_mem0_payload({"_source": "mem0", "memories": []}) is True

    def test_detects_via_memory_field(self) -> None:
        assert is_mem0_payload({"memories": [{"memory": "text"}]}) is True

    def test_rejects_unknown_structure(self) -> None:
        assert is_mem0_payload({"memories": [{"text": "no memory key"}]}) is False
        assert is_mem0_payload({}) is False

    def test_detects_when_leading_item_is_junk(self) -> None:
        """A malformed leading entry must not misroute the batch to unknown."""
        assert (
            is_mem0_payload(
                {"memories": ["not-a-dict", {"memory": "valid"}]},
            )
            is True
        )

    def test_auto_detect_dispatches_to_mem0(self) -> None:
        result = build_memory_import_dry_run(_mem0_payload())
        assert result.summary.source == "mem0"
        assert result.summary.status == "ready"


class TestMem0DualKeyShapes:
    @pytest.mark.parametrize("key", ["memories", "results"])
    def test_both_keys_are_supported(self, key: str) -> None:
        result = dry_run_mem0(_mem0_payload(key=key))
        assert result.summary.source == "mem0"
        assert result.summary.mapped_items == 2
        assert result.summary.unmapped_items == 0

    def test_missing_memories_yields_warning(self) -> None:
        result = dry_run_mem0({"_source": "mem0"})
        assert result.summary.mapped_items == 0
        assert result.summary.status == "missing"
        assert "mem0_no_memories_found" in result.warnings
        assert result.mappings[0].status == "unsupported"


class TestMem0Mapping:
    def test_content_and_metadata_mapping(self) -> None:
        result = dry_run_mem0(_mem0_payload())
        items = result.normalized_data["semantic"]
        assert len(items) == 2

        first = items[0]
        assert first["content"] == "Loves hiking on weekends"
        assert first["importance"] == pytest.approx(0.8)
        assert first["tags"] == ["hobby", "outdoor"]
        assert first["created_at"] == "2026-01-01T00:00:00Z"
        assert first["updated_at"] == "2026-01-02T00:00:00Z"
        assert first["metadata"]["external_source"] == "mem0"
        assert first["metadata"]["external_id"] == "mem-1"

    def test_explicit_importance_is_mapped(self) -> None:
        result = dry_run_mem0(_mem0_payload())
        second = result.normalized_data["semantic"][1]
        assert second["importance"] == 0.3

    def test_missing_importance_falls_back_to_default(self) -> None:
        payload = _mem0_payload(
            memories=[{"memory": "no importance", "metadata": {"tags": []}}]
        )
        result = dry_run_mem0(payload)
        assert result.normalized_data["semantic"][0]["importance"] == 0.5
        # Missing timestamps fall back to a stable non-empty value.
        assert result.normalized_data["semantic"][0]["created_at"]
        assert result.normalized_data["semantic"][0]["updated_at"]

    def test_non_string_tags_are_filtered(self) -> None:
        payload = _mem0_payload(
            memories=[
                {
                    "memory": "tag filtering",
                    "metadata": {"tags": ["keep", 42, None, "drop"]},
                }
            ]
        )
        result = dry_run_mem0(payload)
        tags = result.normalized_data["semantic"][0]["tags"]
        assert tags == ["keep", "drop"]

    def test_text_fallback_when_memory_key_absent(self) -> None:
        payload = {"_source": "mem0", "memories": [{"text": "plain text memory"}]}
        result = dry_run_mem0(payload)
        assert result.normalized_data["semantic"][0]["content"] == "plain text memory"


class TestMem0EdgeCases:
    def test_empty_list_drops_everything(self) -> None:
        result = dry_run_mem0({"_source": "mem0", "memories": []})
        assert result.summary.mapped_items == 0
        assert result.summary.status == "missing"
        assert result.mappings[0].status == "dropped"

    def test_non_dict_items_are_unmapped(self) -> None:
        payload = {"_source": "mem0", "memories": ["not-a-dict", {"memory": "valid"}]}
        result = dry_run_mem0(payload)
        assert result.summary.mapped_items == 1
        assert result.summary.unmapped_items == 1

    def test_empty_content_is_unmapped(self) -> None:
        payload = {"_source": "mem0", "memories": [{"memory": ""}]}
        result = dry_run_mem0(payload)
        assert result.summary.mapped_items == 0
        assert result.summary.unmapped_items == 1


class TestMem0Roundtrip:
    def test_dry_run_through_session_entrypoint(self) -> None:
        """Full pipeline: auto-detect -> dry-run -> semantic bucket."""
        result = build_memory_import_dry_run(_mem0_payload())
        assert result.summary.source == "mem0"
        assert result.summary.status == "ready"
        assert len(result.normalized_data["semantic"]) == 2
        assert all(
            mapping.target_bucket == "semantic" and mapping.status == "mapped"
            for mapping in result.mappings
        )
