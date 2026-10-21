"""Unit tests for gbrain memory import adapter."""

from __future__ import annotations

from app.services.memory.imports.import_adapters import build_memory_import_dry_run
from app.services.memory.imports.import_gbrain import dry_run_gbrain


class TestGbrainDetection:
    """Auto-detection picks gbrain adapter from payload structure."""

    def test_detect_gbrain_via_source_tag(self) -> None:
        payload = {"_source": "gbrain", "gbrain_pages": [{"type": "person", "compiled_truth": "Alice"}]}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "gbrain"

    def test_detect_gbrain_via_pages_key(self) -> None:
        payload = {"gbrain_pages": [{"type": "concept", "compiled_truth": "ML basics"}]}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "gbrain"

    def test_explicit_source_param(self) -> None:
        payload = {"gbrain_pages": [{"type": "note", "compiled_truth": "Quick note"}]}
        result = build_memory_import_dry_run(payload, source="gbrain")
        assert result.summary.source == "gbrain"


class TestGbrainTypeMapping:
    """gbrain page types are correctly mapped to Myrm memory buckets."""

    def test_person_maps_to_profile(self) -> None:
        payload = {
            "gbrain_pages": [
                {"type": "person", "title": "Alice Chen", "compiled_truth": "VP Engineering at TechCo."},
            ]
        }
        result = dry_run_gbrain(payload)
        assert result.normalized_data.get("profile")
        assert len(result.normalized_data["profile"]) == 1

    def test_concept_maps_to_semantic(self) -> None:
        payload = {
            "gbrain_pages": [
                {"type": "concept", "title": "RAG", "compiled_truth": "Retrieval Augmented Generation."},
            ]
        }
        result = dry_run_gbrain(payload)
        assert result.normalized_data.get("semantic")
        assert len(result.normalized_data["semantic"]) == 1

    def test_meeting_maps_to_episodic(self) -> None:
        payload = {
            "gbrain_pages": [
                {"type": "meeting", "title": "Sprint Review", "compiled_truth": "Discussed Q3 goals."},
            ]
        }
        result = dry_run_gbrain(payload)
        assert result.normalized_data.get("episodic")
        assert len(result.normalized_data["episodic"]) == 1

    def test_unknown_type_falls_back_to_semantic(self) -> None:
        payload = {
            "gbrain_pages": [
                {"type": "therapy-session", "title": "Session 5", "compiled_truth": "Discussed anxiety."},
            ]
        }
        result = dry_run_gbrain(payload)
        assert result.normalized_data.get("semantic")
        assert len(result.normalized_data["semantic"]) == 1

    def test_multiple_types_correctly_bucketed(self) -> None:
        payload = {
            "gbrain_pages": [
                {"type": "person", "title": "Bob", "compiled_truth": "CTO"},
                {"type": "company", "title": "AcmeCo", "compiled_truth": "Series B startup"},
                {"type": "concept", "title": "Vector DB", "compiled_truth": "Embedding storage"},
                {"type": "meeting", "title": "Standup", "compiled_truth": "Daily sync"},
                {"type": "email", "title": "RE: Invoice", "compiled_truth": "Please review"},
            ]
        }
        result = dry_run_gbrain(payload)
        assert len(result.normalized_data.get("profile", [])) == 2
        assert len(result.normalized_data.get("semantic", [])) == 1
        assert len(result.normalized_data.get("episodic", [])) == 2
        assert result.summary.mapped_items == 5


class TestGbrainMetadata:
    """Metadata and emotional_weight are correctly preserved."""

    def test_emotional_weight_mapped_to_importance(self) -> None:
        payload = {
            "gbrain_pages": [
                {"type": "person", "title": "VIP", "compiled_truth": "Key contact", "frontmatter": {"emotional_weight": 0.95}},
            ]
        }
        result = dry_run_gbrain(payload)
        item = result.normalized_data["profile"][0]
        assert item["importance"] == 0.95

    def test_tags_preserved(self) -> None:
        payload = {
            "gbrain_pages": [
                {"type": "concept", "title": "FastAPI", "compiled_truth": "Web framework", "tags": ["python", "web"]},
            ]
        }
        result = dry_run_gbrain(payload)
        item = result.normalized_data["semantic"][0]
        assert "python" in item["tags"]
        assert "web" in item["tags"]
        assert "gbrain" in item["tags"]

    def test_timeline_included_in_content(self) -> None:
        payload = {
            "gbrain_pages": [
                {
                    "type": "project",
                    "title": "Alpha",
                    "compiled_truth": "Current state.",
                    "timeline": "2024-01: Started\n2024-06: Shipped",
                },
            ]
        }
        result = dry_run_gbrain(payload)
        item = result.normalized_data["semantic"][0]
        assert "2024-01: Started" in str(item["content"])


class TestGbrainEdgeCases:
    """Edge cases and error handling."""

    def test_empty_pages_returns_warning(self) -> None:
        payload = {"gbrain_pages": []}
        result = dry_run_gbrain(payload)
        assert result.summary.status == "missing"
        assert "gbrain_no_pages" in result.warnings

    def test_missing_pages_key(self) -> None:
        payload = {"_source": "gbrain"}
        result = dry_run_gbrain(payload)
        assert result.summary.status == "missing"

    def test_pages_with_missing_type_skipped(self) -> None:
        payload = {
            "gbrain_pages": [
                {"title": "No type", "compiled_truth": "Should be skipped"},
                {"type": "note", "title": "Valid", "compiled_truth": "Kept"},
            ]
        }
        result = dry_run_gbrain(payload)
        assert result.summary.mapped_items == 1

    def test_mapping_summary_per_type(self) -> None:
        payload = {
            "gbrain_pages": [
                {"type": "person", "title": "A", "compiled_truth": "a"},
                {"type": "person", "title": "B", "compiled_truth": "b"},
                {"type": "concept", "title": "C", "compiled_truth": "c"},
            ]
        }
        result = dry_run_gbrain(payload)
        mapping_sources = [m.source_bucket for m in result.mappings]
        assert "gbrain/person" in mapping_sources
        assert "gbrain/concept" in mapping_sources
