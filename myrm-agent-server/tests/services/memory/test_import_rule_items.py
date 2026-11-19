"""An imported rule is one the memory store accepts, carries no keyword field and keeps where it came from.

``MemoryManager.import_memories`` parses every rule with ``ProceduralMemory`` and drops the one that fails, so a rule
item needs a ``trigger`` and an ``action`` to be stored at all. A rule is found by its trigger and action text, so no
importer invents a ``trigger_keywords`` list (a source tag, a glob, a model-written trigger) that nothing reads; the
source stays in ``metadata.external_*``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from myrm_agent_harness.toolkits.memory import ProceduralMemory

from app.services.memory.imports.import_adapter_utils import DEFAULT_RULE_TRIGGER, RULE_ACTION_MAX_CHARS
from app.services.memory.imports.import_adapters import RequestedImportSource, build_memory_import_dry_run
from app.services.memory.imports.import_claude_code_parser import errors_to_procedural
from app.services.memory.imports.import_pasted_model import dry_run_pasted_model_items

type RuleItems = list[dict[str, object]]


def _adapter_rules(payload: dict[str, object], source: RequestedImportSource = "auto") -> RuleItems:
    result = build_memory_import_dry_run(payload, source=source)
    return list(result.normalized_data["procedural"])


def _pasted_model_rules() -> RuleItems:
    items: list[object] = [{"content": "Run tests before merge", "bucket": "procedural", "trigger": "deploy"}]
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


@pytest.mark.parametrize("rule_items", [pytest.param(build, id=name) for name, build, _source in IMPORTERS])
def test_an_imported_rule_is_one_the_store_accepts(rule_items: Callable[[], RuleItems]) -> None:
    items = rule_items()

    assert items, "the importer produced no rule"
    for item in items:
        # The parse ``import_memories`` applies: a rule it rejects is previewed as mapped, then never stored.
        rule = ProceduralMemory.model_validate({key: value for key, value in item.items() if key not in ("id", "embedding")})
        assert rule.trigger.strip()
        assert rule.action.strip()


def test_a_model_written_trigger_is_the_trigger_of_its_rule() -> None:
    assert _pasted_model_rules()[0]["trigger"] == "deploy"


def test_a_rule_without_a_stated_condition_applies_to_every_project() -> None:
    rule = dry_run_pasted_model_items([{"content": "Run tests before merge", "bucket": "procedural"}]).normalized_data
    blank = dry_run_pasted_model_items([{"content": "Run tests", "bucket": "procedural", "trigger": "  "}]).normalized_data

    assert rule["procedural"][0]["trigger"] == DEFAULT_RULE_TRIGGER
    assert blank["procedural"][0]["trigger"] == DEFAULT_RULE_TRIGGER


def test_a_long_rule_keeps_its_text_and_caps_its_action() -> None:
    item = dry_run_pasted_model_items([{"content": "x" * 600, "bucket": "procedural"}]).normalized_data["procedural"][0]

    assert item["content"] == "x" * 600
    assert item["action"] == "x" * RULE_ACTION_MAX_CHARS
