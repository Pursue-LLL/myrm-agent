"""An imported rule carries no keyword field of its own and keeps where it came from in its metadata.

A rule is found by its trigger and action text, so no importer invents a ``trigger_keywords`` list (a source tag, a
glob, a model-written trigger) that nothing reads; the source stays in ``metadata.external_*``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.services.memory.imports.import_adapters import RequestedImportSource, build_memory_import_dry_run
from app.services.memory.imports.import_claude_code_parser import errors_to_procedural
from app.services.memory.imports.import_pasted_model import dry_run_pasted_model_items

type RuleItems = list[dict[str, object]]


def _adapter_rules(payload: dict[str, object], source: RequestedImportSource = "auto") -> RuleItems:
    result = build_memory_import_dry_run(payload, source=source)
    return list(result.normalized_data["procedural"])


def _pasted_model_rules() -> RuleItems:
    items = [{"content": "Run tests before merge", "bucket": "procedural", "trigger": "deploy"}]
    return list(dry_run_pasted_model_items(items).normalized_data["procedural"])


# (importer, how it produces rule items, the ``external_source`` its metadata names)
IMPORTERS: list[tuple[str, Callable[[], RuleItems], str]] = [
    (
        "trae",
        lambda: _adapter_rules(
            {"_source": "trae", "trae_rules": [{"name": "User Rule", "content": "Prefer small functions", "scope": "user"}]}
        ),
        "trae",
    ),
    (
        "cursor",
        lambda: _adapter_rules(
            {"_source": "cursor", "cursor_rules": [{"name": "Style", "content": "Use tabs", "globs": "*.py"}]}
        ),
        "cursor",
    ),
    ("codex", lambda: _adapter_rules({"_source": "codex", "codex_instructions": "be helpful and concise"}), "codex"),
    (
        "agentmemory",
        lambda: _adapter_rules(
            {
                "version": "0.5.0",
                "proceduralMemories": [{"id": "p1", "name": "Deploy", "steps": ["build", "ship"], "concepts": ["ci"]}],
            },
            source="agentmemory",
        ),
        "agentmemory",
    ),
    (
        "plur",
        lambda: _adapter_rules(
            {
                "_source": "plur",
                "engrams": [{"id": "e1", "type": "procedural", "statement": "Run tests", "status": "active"}],
            }
        ),
        "plur",
    ),
    (
        "pasted",
        lambda: _adapter_rules(
            {"_source": "pasted_memory", "text": "## Rules\n- [2026-01-05] Always run tests before merge\n"},
            source="pasted_memory",
        ),
        "pasted_memory",
    ),
    ("pasted_model", _pasted_model_rules, "pasted_memory"),
    ("claude_code", lambda: errors_to_procedural([{"error": "boom happened"}]), "claude_code_jsonl"),
]


@pytest.mark.parametrize(("rule_items", "external_source"), [pytest.param(b, s, id=n) for n, b, s in IMPORTERS])
def test_an_imported_rule_invents_no_keywords_and_keeps_its_source(
    rule_items: Callable[[], RuleItems], external_source: str
) -> None:
    items = rule_items()

    assert items, "the importer produced no rule"
    for item in items:
        assert "trigger_keywords" not in item
        metadata = item["metadata"]
        assert isinstance(metadata, dict)
        assert metadata["external_source"] == external_source
