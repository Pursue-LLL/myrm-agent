"""Unit tests for the PLUR engram import adapter (Open Engram Standard v1).

[INPUT]
Official PLUR store payloads: parsed ``engrams`` lists and ``raw_yaml`` text.

[OUTPUT]
Verified MemoryImportDryRunResult mappings to procedural and semantic buckets,
inactive-state skipping, and dispatch through import_adapters.

[POS]
Unit tests for app.services.memory.imports.import_plur and the pasted-free
dispatch path in import_adapters.
"""

from __future__ import annotations

from app.services.memory.imports.import_adapters import build_memory_import_dry_run
from app.services.memory.imports.import_plur import dry_run_plur, is_plur_payload

_ACTIVE_ENGRAM = {
    "id": "ENG-2026-05-06-001",
    "statement": "Always use Pydantic v2 BaseModels with strict types",
    "type": "behavioral",
    "status": "active",
    "scope": "global",
    "visibility": "private",
    "domain": "backend",
    "created_at": "2026-05-06T08:30:00Z",
}
_ARCHITECTURAL_ENGRAM = {
    "id": "ENG-2026-05-06-002",
    "statement": "Monorepo backend lives in myrm-agent/myrm-agent-server",
    "type": "architectural",
    "status": "active",
    "scope": "project:open-perplexity",
    "domain": "repo",
}
_RETIRED_ENGRAM = {
    "id": "ENG-2026-05-06-003",
    "statement": "Old deploy checklist superseded by the pipeline",
    "type": "procedural",
    "status": "retired",
    "scope": "global",
    "domain": "ops",
}


def test_is_plur_payload_detection() -> None:
    """Detection must key on the official engram shape, not on a guessed legacy one."""

    assert is_plur_payload({"_source": "plur"}) is True
    assert is_plur_payload({"engrams": [_ACTIVE_ENGRAM]}) is True
    assert is_plur_payload({"raw_yaml": "engrams:\n  - id: ENG-1\n    statement: hello\n"}) is True
    assert is_plur_payload({"other": 123}) is False
    assert is_plur_payload({"engrams": [{"text": "no statement field"}]}) is False


def test_dry_run_plur_empty_payload() -> None:
    """Verify empty payload returns a clear warning and an explicit reason."""

    res = dry_run_plur({})

    assert res.summary.source == "plur"
    assert res.summary.mapped_items == 0
    assert "plur_no_engrams_found" in res.warnings
    assert res.mappings and res.mappings[0].reason


def test_dry_run_plur_maps_types_and_skips_inactive() -> None:
    """behavioral/procedural → procedural rules; architectural → semantic facts."""

    res = dry_run_plur({"engrams": [_ACTIVE_ENGRAM, _ARCHITECTURAL_ENGRAM, _RETIRED_ENGRAM]})

    assert res.summary.source == "plur"
    assert res.summary.status == "warning"
    assert res.summary.mapped_items == 2
    assert res.summary.unmapped_items == 1
    assert "plur_inactive_skipped" in res.warnings
    skipped_row = next(item for item in res.mappings if item.status == "dropped")
    assert "lifecycle" in skipped_row.reason

    procedural = res.normalized_data["procedural"]
    assert procedural[0]["content"] == _ACTIVE_ENGRAM["statement"]
    assert procedural[0]["priority"] == 5
    assert procedural[0]["created_at"] == "2026-05-06T08:30:00Z"
    assert procedural[0]["metadata"]["external_id"] == "ENG-2026-05-06-001"
    assert procedural[0]["metadata"]["external_domain"] == "backend"

    semantic = res.normalized_data["semantic"]
    assert semantic[0]["content"] == _ARCHITECTURAL_ENGRAM["statement"]
    assert semantic[0]["tags"] == ["plur", "repo", "architectural"]


def test_dry_run_plur_does_not_synthesize_missing_timestamps() -> None:
    """The standard forbids synthesizing created_at; the adapter must not invent one."""

    res = dry_run_plur({"engrams": [_ARCHITECTURAL_ENGRAM]})

    assert res.summary.mapped_items == 1
    item = res.normalized_data["semantic"][0]
    # The adapter stamps the record time; the engram's own date stays absent.
    assert item["metadata"]["external_id"] == "ENG-2026-05-06-002"
    assert "external_created_at" not in item["metadata"]


def test_dry_run_plur_raw_yaml_official_store() -> None:
    """A raw engrams.yaml body parses through the official store shape."""

    raw_yaml = (
        "engrams:\n"
        "  - id: ENG-2026-05-06-001\n"
        '    statement: "Deploys wait for migrations"\n'
        "    type: architectural\n"
        "    status: active\n"
        "    scope: global\n"
    )

    res = dry_run_plur({"raw_yaml": raw_yaml})

    assert res.summary.mapped_items == 1
    assert res.normalized_data["semantic"][0]["content"] == "Deploys wait for migrations"


def test_invalid_engrams_without_statement_are_skipped() -> None:
    res = dry_run_plur({"engrams": [{"id": "ENG-1", "type": "behavioral", "status": "active"}]})

    assert res.summary.mapped_items == 0
    assert res.summary.unmapped_items == 1
    assert "plur_invalid_engrams" in res.warnings


def test_dispatch_via_build_memory_import_dry_run() -> None:
    """auto-detected PLUR payloads dispatch to the plur adapter and keep the label."""

    payload = {"_source": "plur", "engrams": [_ACTIVE_ENGRAM]}

    res = build_memory_import_dry_run(payload, "auto")

    assert res.summary.source == "plur"
    assert res.summary.mapped_items == 1
