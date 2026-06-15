"""Unit tests for import_adapters.py — dry-run adapter for all supported formats.

Validates source detection, structural mapping, quality grading, edge-case
handling, and provenance metadata across native JSON, myrm-archive, AgentMemory,
Claude Code JSONL, and unsupported payloads.
"""

from __future__ import annotations

import pytest

from app.services.memory.import_adapter_utils import (
    SUPPORTED_NATIVE_BUCKETS,
    WARNING_AGENTMEMORY_TOO_MANY_MEMORIES,
    WARNING_AGENTMEMORY_VERSION_UNSUPPORTED,
    WARNING_GRAPH_SKIPPED,
    WARNING_MYRM_ARCHIVE_MEMORY_SECTION_MISSING,
    WARNING_MYRM_ARCHIVE_REVIEW_ONLY_SECTIONS,
    WARNING_NO_NATIVE_BUCKETS,
    WARNING_UNSUPPORTED_SOURCE,
)
from app.services.memory.import_adapters import build_memory_import_dry_run


class TestSourceDetection:
    """Auto-detection picks the correct adapter."""

    def test_detect_native_json_via_data_key(self) -> None:
        payload = {"data": {"semantic": [{"content": "hello"}]}}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "native_json"

    def test_detect_native_json_via_bucket_keys(self) -> None:
        payload = {"semantic": [{"content": "hi"}], "episodic": []}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "native_json"

    def test_detect_myrm_archive(self) -> None:
        payload = {
            "manifest": {"format": "myrm_memory_archive", "version": "1"},
            "data": {"memory": {"semantic": [{"content": "x"}]}},
        }
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "myrm_archive"

    def test_detect_agentmemory(self) -> None:
        payload = {
            "version": "0.5.0",
            "sessions": [],
            "observations": {},
            "memories": [{"title": "t", "content": "c"}],
            "summaries": [],
        }
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "agentmemory"

    def test_detect_claude_code_jsonl(self) -> None:
        payload = {
            "jsonl_lines": [
                {"type": "user", "message": {"content": "hello"}},
                {"type": "assistant", "message": {"content": "hi"}},
            ]
        }
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "claude_code_jsonl"

    def test_unknown_payload_returns_unsupported(self) -> None:
        payload = {"random_key": 123}
        result = build_memory_import_dry_run(payload)
        assert result.summary.status == "missing"
        assert WARNING_UNSUPPORTED_SOURCE in result.warnings

    def test_explicit_source_overrides_auto(self) -> None:
        payload = {"semantic": [{"content": "test"}]}
        result = build_memory_import_dry_run(payload, source="native_json")
        assert result.summary.source == "native_json"


class TestNativeJsonDryRun:
    """Native JSON adapter maps supported buckets and rejects unsupported."""

    def test_single_bucket_mapped(self) -> None:
        payload = {"semantic": [{"content": "fact 1"}, {"content": "fact 2"}]}
        result = build_memory_import_dry_run(payload, source="native_json")
        assert result.summary.status == "ready"
        assert result.summary.mapped_items == 2
        assert result.summary.unmapped_items == 0
        assert "semantic" in result.normalized_data
        assert len(result.normalized_data["semantic"]) == 2

    def test_all_supported_buckets(self) -> None:
        payload = {bucket: [{"content": f"{bucket} item"}] for bucket in SUPPORTED_NATIVE_BUCKETS}
        result = build_memory_import_dry_run(payload, source="native_json")
        assert result.summary.status == "ready"
        assert result.summary.mapped_items == len(SUPPORTED_NATIVE_BUCKETS)
        for bucket in SUPPORTED_NATIVE_BUCKETS:
            assert bucket in result.normalized_data

    def test_unsupported_bucket_flagged(self) -> None:
        payload = {"custom_bucket": [{"content": "x"}], "semantic": [{"content": "y"}]}
        result = build_memory_import_dry_run(payload, source="native_json")
        assert result.summary.status == "warning"
        assert result.summary.mapped_items == 1
        assert result.summary.unmapped_items == 1
        unsupported = [m for m in result.mappings if m.status == "unsupported"]
        assert len(unsupported) == 1
        assert unsupported[0].source_bucket == "custom_bucket"

    def test_non_object_rows_dropped(self) -> None:
        payload = {"semantic": [{"content": "ok"}, "not_a_dict", 42]}
        result = build_memory_import_dry_run(payload, source="native_json")
        assert result.summary.mapped_items == 1
        assert result.summary.unmapped_items == 2

    def test_empty_payload_warns(self) -> None:
        result = build_memory_import_dry_run({}, source="native_json")
        assert result.summary.status == "missing"
        assert WARNING_NO_NATIVE_BUCKETS in result.warnings


class TestMrmArchiveDryRun:
    """Myrm archive adapter delegates memory section to native pipeline."""

    def test_archive_with_memory_section(self) -> None:
        payload = {
            "manifest": {"format": "myrm_memory_archive", "version": "2"},
            "data": {"memory": {"semantic": [{"content": "archived fact"}]}},
        }
        result = build_memory_import_dry_run(payload, source="myrm_archive")
        assert result.summary.source == "myrm_archive"
        assert result.summary.mapped_items == 1
        assert "semantic" in result.normalized_data

    def test_archive_missing_memory_section(self) -> None:
        payload = {
            "manifest": {"format": "myrm_memory_archive"},
            "data": {},
        }
        result = build_memory_import_dry_run(payload, source="myrm_archive")
        assert WARNING_MYRM_ARCHIVE_MEMORY_SECTION_MISSING in result.warnings

    def test_review_only_sections_flagged(self) -> None:
        payload = {
            "manifest": {"format": "myrm_memory_archive"},
            "data": {
                "memory": {"semantic": [{"content": "x"}]},
                "conversation": [{"id": "c1"}],
                "audit": [{"id": "a1"}],
            },
        }
        result = build_memory_import_dry_run(payload, source="myrm_archive")
        assert WARNING_MYRM_ARCHIVE_REVIEW_ONLY_SECTIONS in result.warnings
        review_only = [m for m in result.mappings if "archive." in m.source_bucket]
        assert len(review_only) == 2


class TestAgentMemoryDryRun:
    """AgentMemory adapter maps memories, summaries, observations, and procedural."""

    def test_basic_agentmemory_mapping(self) -> None:
        payload = {
            "version": "0.5.0",
            "sessions": [{"id": "s1"}],
            "memories": [{"title": "Fact", "content": "User likes coffee"}],
            "summaries": [{"title": "Summary", "narrative": "Discussed preferences"}],
            "observations": {"s1": [{"title": "Obs", "facts": ["likes coffee"]}]},
        }
        result = build_memory_import_dry_run(payload, source="agentmemory")
        assert result.summary.source == "agentmemory"
        assert result.summary.mapped_items >= 3
        assert "semantic" in result.normalized_data
        assert "episodic" in result.normalized_data

    def test_semantic_memories_merged(self) -> None:
        payload = {
            "version": "0.5.0",
            "sessions": [],
            "memories": [{"title": "M1", "content": "c1"}],
            "summaries": [],
            "observations": {},
            "semanticMemories": [{"fact": "User is a developer"}],
        }
        result = build_memory_import_dry_run(payload, source="agentmemory")
        assert len(result.normalized_data.get("semantic", [])) == 2

    def test_procedural_memories_mapped(self) -> None:
        payload = {
            "version": "0.5.0",
            "sessions": [],
            "memories": [],
            "summaries": [],
            "observations": {},
            "proceduralMemories": [{"name": "Deploy", "steps": ["build", "push"], "triggerCondition": "deploy request"}],
        }
        result = build_memory_import_dry_run(payload, source="agentmemory")
        assert "procedural" in result.normalized_data
        assert len(result.normalized_data["procedural"]) == 1

    def test_unsupported_version_rejected(self) -> None:
        payload = {
            "version": "0.2.0",
            "sessions": [],
            "memories": [],
            "summaries": [],
            "observations": {},
        }
        result = build_memory_import_dry_run(payload, source="agentmemory")
        assert WARNING_AGENTMEMORY_VERSION_UNSUPPORTED in result.warnings

    def test_graph_data_skipped_with_warning(self) -> None:
        payload = {
            "version": "0.5.0",
            "sessions": [],
            "memories": [],
            "summaries": [],
            "observations": {},
            "graphNodes": [{"id": "n1"}],
            "graphEdges": [{"from": "n1", "to": "n2"}],
        }
        result = build_memory_import_dry_run(payload, source="agentmemory")
        assert WARNING_GRAPH_SKIPPED in result.warnings

    def test_too_many_memories_rejected(self) -> None:
        payload = {
            "version": "0.5.0",
            "sessions": [],
            "memories": [{"title": f"M{i}", "content": f"c{i}"} for i in range(50_001)],
            "summaries": [],
            "observations": {},
        }
        result = build_memory_import_dry_run(payload, source="agentmemory")
        assert WARNING_AGENTMEMORY_TOO_MANY_MEMORIES in result.warnings

    def test_metadata_provenance_attached(self) -> None:
        payload = {
            "version": "0.5.0",
            "sessions": [],
            "memories": [{"id": "mem-1", "title": "T", "content": "C", "type": "fact"}],
            "summaries": [],
            "observations": {},
        }
        result = build_memory_import_dry_run(payload, source="agentmemory")
        semantic = result.normalized_data["semantic"][0]
        assert semantic["metadata"]["external_source"] == "agentmemory"
        assert semantic["metadata"]["external_id"] == "mem-1"


class TestExternalSourceDetection:
    """Auto-detection routes external source payloads to the correct adapter."""

    def test_detect_hermes_via_source_tag(self) -> None:
        payload = {"_source": "hermes", "memory_md": "- fact"}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "hermes"

    def test_detect_hermes_via_payload_keys(self) -> None:
        payload = {"soul_md": "I am helpful", "memory_md": "- fact"}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "hermes"

    def test_openclaw_source_tag_wins_over_shared_markdown_keys(self) -> None:
        payload = {
            "_source": "openclaw",
            "memory_md": "- workspace fact",
            "user_md": "- engineer",
            "openclaw_sessions": [{"title": "Sprint", "summary": "Shipped"}],
        }
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "openclaw"
        buckets = {mapping.source_bucket for mapping in result.mappings}
        assert "openclaw_sessions" in buckets

    def test_detect_openclaw_via_source_tag(self) -> None:
        payload = {"_source": "openclaw", "openclaw_memory": [{"content": "fact"}]}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "openclaw"

    def test_detect_openclaw_via_payload_keys(self) -> None:
        payload = {"openclaw_sessions": [{"title": "s", "messages": []}]}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "openclaw"

    def test_detect_cursor_via_source_tag(self) -> None:
        payload = {"_source": "cursor_rules", "cursor_rules": [{"name": "r", "content": "c"}]}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "cursor_rules"

    def test_detect_cursor_via_payload_keys(self) -> None:
        payload = {"cursor_rules": [{"name": "r", "content": "c"}]}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "cursor_rules"

    def test_detect_codex_via_source_tag(self) -> None:
        payload = {"_source": "codex", "codex_instructions": "be helpful"}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "codex"

    def test_detect_codex_via_payload_keys(self) -> None:
        payload = {"codex_instructions": "use type hints"}
        result = build_memory_import_dry_run(payload)
        assert result.summary.source == "codex"

    def test_explicit_hermes_source_overrides(self) -> None:
        payload = {"memory_md": "- fact"}
        result = build_memory_import_dry_run(payload, source="hermes")
        assert result.summary.source == "hermes"

    def test_explicit_openclaw_source_overrides(self) -> None:
        payload = {"openclaw_memory": [{"content": "fact"}]}
        result = build_memory_import_dry_run(payload, source="openclaw")
        assert result.summary.source == "openclaw"

    def test_explicit_cursor_source_overrides(self) -> None:
        payload = {"cursor_rules": [{"name": "r", "content": "c"}]}
        result = build_memory_import_dry_run(payload, source="cursor_rules")
        assert result.summary.source == "cursor_rules"

    def test_explicit_codex_source_overrides(self) -> None:
        payload = {"codex_instructions": "test"}
        result = build_memory_import_dry_run(payload, source="codex")
        assert result.summary.source == "codex"


class TestAdapterRegistryConsistency:
    """Verify adapter registry matches actual adapter capabilities."""

    def test_registry_sources_include_all_ready_adapters(self) -> None:
        from app.services.memory.import_adapter_registry import (
            memory_import_adapter_status,
            memory_import_supported_sources,
        )

        sources = memory_import_supported_sources()
        statuses = memory_import_adapter_status()
        ready = [s for s, st in statuses.items() if st == "ready"]
        for adapter in ready:
            assert adapter in sources, f"Ready adapter '{adapter}' missing from supported sources"

    def test_dry_run_handles_all_ready_sources(self) -> None:
        """Every 'ready' source should produce a valid result (not crash)."""
        from app.services.memory.import_adapter_registry import memory_import_adapter_status

        statuses = memory_import_adapter_status()
        ready_sources = [s for s, st in statuses.items() if st == "ready"]
        assert len(ready_sources) >= 4, "Should have at least 4 ready adapters"

    def test_source_adapters_are_ready(self) -> None:
        from app.services.memory.import_adapter_registry import memory_import_adapter_status

        statuses = memory_import_adapter_status()
        for source in ("hermes", "openclaw", "cursor", "codex"):
            assert statuses.get(source) == "ready", f"{source} adapter should be ready"

    def test_claude_competitor_instruction_only_lane(self) -> None:
        """After split, memory lane is empty; explicit claude source yields ready dry-run."""
        payload = {"_source": "claude"}
        result = build_memory_import_dry_run(payload, source="claude")
        assert result.summary.source == "claude"
        assert result.summary.status == "ready"
        assert result.summary.mapped_items == 0


class TestEdgeCases:
    """Edge cases and robustness."""

    def test_nested_data_key_native(self) -> None:
        payload = {"version": "1", "data": {"semantic": [{"content": "nested"}]}}
        result = build_memory_import_dry_run(payload, source="native_json")
        assert result.summary.mapped_items == 1

    def test_empty_agentmemory_valid(self) -> None:
        payload = {
            "version": "0.5.0",
            "sessions": [],
            "memories": [],
            "summaries": [],
            "observations": {},
        }
        result = build_memory_import_dry_run(payload, source="agentmemory")
        assert result.summary.status == "missing"
        assert result.summary.mapped_items == 0

    def test_strength_to_score_conversion(self) -> None:
        payload = {
            "version": "0.5.0",
            "sessions": [],
            "memories": [{"title": "T", "content": "C", "strength": 8}],
            "summaries": [],
            "observations": {},
        }
        result = build_memory_import_dry_run(payload, source="agentmemory")
        semantic = result.normalized_data["semantic"][0]
        assert semantic["importance"] == pytest.approx(0.8, abs=0.01)
