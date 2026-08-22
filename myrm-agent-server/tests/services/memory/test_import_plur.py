"""Unit tests for PLUR engram memory import adapter.

[INPUT]
PLUR engram data payloads (JSON list, nested engrams, plain YAML, scoped rules).

[OUTPUT]
Verified MemoryImportDryRunResult mappings to semantic and profile memory buckets.

[POS]
Unit tests for app.services.memory.imports.import_plur and dispatch via import_adapters.
"""

from __future__ import annotations

from app.services.memory.imports.import_adapters import build_memory_import_dry_run
from app.services.memory.imports.import_plur import dry_run_plur, is_plur_payload


def test_is_plur_payload_detection() -> None:
    """Verify PLUR payload detection heuristics."""
    assert is_plur_payload({"_source": "plur"}) is True
    assert is_plur_payload({"plur_engrams": []}) is True
    assert is_plur_payload({"engrams": []}) is True
    assert is_plur_payload({"raw_yaml": "domain: coding\nengrams:\n  - text: Use bun"}) is True
    assert is_plur_payload({"other": 123}) is False


def test_dry_run_plur_empty_payload() -> None:
    """Verify empty payload returns clear warning and 0 mapped items."""
    res = dry_run_plur({})
    assert res.summary.source == "plur"
    assert res.summary.total_items == 0
    assert res.summary.mapped_items == 0
    assert "plur_no_engrams_found" in res.warnings


def test_dry_run_plur_structured_list() -> None:
    """Verify structured list with global preference and project scope."""
    payload: dict[str, object] = {
        "_source": "plur",
        "plur_engrams": [
            {
                "content": "User prefers concise answers",
                "domain": "communication",
                "scope": "global",
                "type": "preference",
                "id": "eng-1",
            },
            {
                "content": "Project uses FastAPI and Pydantic v2",
                "domain": "backend",
                "scope": "project:open-perplexity",
                "type": "fact",
                "id": "eng-2",
            },
        ],
    }

    res = dry_run_plur(payload)
    assert res.summary.source == "plur"
    assert res.summary.mapped_items == 2
    assert "profile" in res.normalized_data
    assert "semantic" in res.normalized_data
    assert len(res.normalized_data["profile"]) == 1
    assert len(res.normalized_data["semantic"]) == 1
    assert res.normalized_data["profile"][0]["content"] == "User prefers concise answers"
    assert res.normalized_data["semantic"][0]["content"] == "Project uses FastAPI and Pydantic v2"


def test_dry_run_plur_yaml_string() -> None:
    """Verify parsing raw YAML string payload safely."""
    raw_yaml = """
- domain: frontend
  scope: global
  type: preference
  content: Never use raw emoji in UI components
  timestamp: "2026-08-20T10:00:00Z"
- domain: testing
  scope: project:myrm
  type: rule
  content: Always run pytest via run-pytest-safe.sh
"""
    payload: dict[str, object] = {
        "raw_yaml": raw_yaml,
    }

    res = dry_run_plur(payload)
    assert res.summary.mapped_items == 2
    assert len(res.normalized_data.get("profile", [])) == 1
    assert len(res.normalized_data.get("semantic", [])) == 1


def test_dispatch_via_build_memory_import_dry_run() -> None:
    """Verify general dispatcher routes to PLUR adapter."""
    payload: dict[str, object] = {
        "_source": "plur",
        "engrams": [{"content": "Always format code with ruff", "scope": "global", "type": "rule"}],
    }

    res = build_memory_import_dry_run(payload)
    assert res.summary.source == "plur"
    assert res.summary.mapped_items == 1


def test_dry_run_plur_corrupted_yaml_handling() -> None:
    """Verify invalid YAML gracefully falls back to empty result with warning."""
    corrupted_yaml = ":::invalid-yaml-syntax"
    payload: dict[str, object] = {
        "raw_yaml": corrupted_yaml,
    }
    res = dry_run_plur(payload)
    assert res.summary.source == "plur"
    assert res.summary.mapped_items == 0
    assert "plur_no_engrams_found" in res.warnings


def test_dry_run_plur_nested_dict_engrams() -> None:
    """Verify parsing dictionary payload with top-level 'engrams' list."""
    payload: dict[str, object] = {
        "raw_yaml": """
engrams:
  - content: Prefer FastAPI over Flask
    domain: backend
    scope: global
    type: preference
  - content: Use Tailwind v4 for all styles
    domain: frontend
    scope: project:web
    type: rule
"""
    }
    res = dry_run_plur(payload)
    assert res.summary.mapped_items == 2
    assert len(res.normalized_data.get("profile", [])) == 1
    assert len(res.normalized_data.get("semantic", [])) == 1
