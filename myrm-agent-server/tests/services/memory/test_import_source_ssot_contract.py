"""Contract test: the canonical import source vocabulary drives every layer.

Guards the class of drift that previously broke Pi previews (HTTP 422) and
mislabeled Pi imports as Hermes: the migration manifest, the API request schema
and the adapter dispatcher must all agree with
``app.schemas.memory.import_sources``.
"""

from __future__ import annotations

import pytest

from app.schemas.memory.archive import MemoryImportDryRunRequest
from app.schemas.memory.import_sources import IMPORT_SOURCE_IDS, import_source_label
from app.services.memory.imports.import_adapters import (
    _MIGRATION_SOURCE_TO_ADAPTER,
    build_memory_import_dry_run,
)
from app.services.migration.source.source_manifest import (
    migration_source_import_map,
    migration_source_manifest_entries,
)

_MINIMAL_MANIFEST_PAYLOADS: dict[str, dict[str, object]] = {
    "hermes": {"_source": "hermes", "memory_md": "- Prefers concise answers"},
    "openclaw": {"_source": "openclaw", "openclaw_memory": [{"content": "Uses dark mode"}]},
    "claude": {"_source": "claude", "semantic": [{"content": "Feedback: no git confirm"}]},
    "codex": {"_source": "codex", "codex_memory": [{"content": "Deploys wait for migrations"}]},
    "chatgpt": {
        "_source": "chatgpt",
        "conversations": [
            {
                "id": "c1",
                "title": "Topic",
                "create_time": 1700000000,
                "current_node": "n1",
                "mapping": {"n1": {"message": {"author": {"role": "user"}, "content": {"parts": ["hello"]}}}},
            },
        ],
    },
    "gbrain": {"_source": "gbrain", "gbrain_pages": [{"type": "concept", "title": "T", "compiled_truth": "body"}]},
    "pi": {
        "_source": "pi",
        "pi_sessions": [{"id": "s1", "messages": [{"role": "user", "content": "hello"}], "timestamp": "2024-01-01"}],
    },
    "plur": {
        "_source": "plur",
        "engrams": [
            {
                "id": "ENG-2026-05-06-001",
                "statement": "Deploys wait for migrations",
                "type": "architectural",
                "status": "active",
                "scope": "global",
            },
        ],
    },
}


def test_manifest_sources_map_into_the_canonical_vocabulary() -> None:
    mapping = migration_source_import_map()
    assert set(_MINIMAL_MANIFEST_PAYLOADS) == set(mapping), "manifest and payload fixtures drifted"
    for source_id, import_source in mapping.items():
        assert import_source in IMPORT_SOURCE_IDS, f"{source_id} maps to unknown import source {import_source}"


def test_manifest_entries_are_unique() -> None:
    ids = [entry.id for entry in migration_source_manifest_entries()]
    assert len(ids) == len(set(ids))


def test_adapter_dispatch_map_only_uses_canonical_sources() -> None:
    for source_id, adapter_source in _MIGRATION_SOURCE_TO_ADAPTER.items():
        assert adapter_source in IMPORT_SOURCE_IDS, f"{source_id} maps to {adapter_source} outside the canonical set"


@pytest.mark.parametrize("source", IMPORT_SOURCE_IDS)
def test_api_schema_accepts_every_canonical_source(source: str) -> None:
    request = MemoryImportDryRunRequest(source=source, payload={})
    assert request.source == source


@pytest.mark.parametrize("source_id", sorted(_MINIMAL_MANIFEST_PAYLOADS))
def test_manifest_sources_are_dispatchable_and_labelled(source_id: str) -> None:
    """Each manifest source reaches its adapter and reports its own label."""

    expected = migration_source_import_map()[source_id]
    result = build_memory_import_dry_run(_MINIMAL_MANIFEST_PAYLOADS[source_id], expected)
    assert result.summary.source == expected
    assert result.summary.status == "ready"


def test_pi_import_reports_pi_label_and_mapping_counts() -> None:
    """Regression guard: Pi must never be reported as Hermes, and counts must survive."""

    result = build_memory_import_dry_run(_MINIMAL_MANIFEST_PAYLOADS["pi"], "pi")
    assert result.summary.source == "pi"
    assert result.summary.mapped_items == 1
    pi_mapping = next(item for item in result.mappings if item.source_bucket == "pi_sessions")
    assert pi_mapping.item_count == 1
    assert pi_mapping.imported_count == 1


@pytest.mark.parametrize(
    ("source", "expected_label"),
    [
        ("native_json", "native-json"),
        ("claude_code_jsonl", "claude-code"),
        ("cursor_rules", "cursor"),
        ("pasted_memory", "pasted-memory"),
        ("hermes", "hermes"),
    ],
)
def test_import_source_labels_are_stable(source: str, expected_label: str) -> None:
    assert import_source_label(source) == expected_label
