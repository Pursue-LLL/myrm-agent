"""Unit tests for the pasted free-text memory import adapter."""

from __future__ import annotations

from app.services.memory.imports.import_pasted import (
    MAX_PASTED_ENTRIES,
    MAX_PASTED_TEXT_CHARS,
    dry_run_pasted_memory,
)
from app.services.memory.imports.import_pasted_model import dry_run_pasted_model_items

_PROMPT_SHAPED_TEXT = """Here is the export you asked for:

```
## RULES
[2024-03-01] - Always answer in Chinese when I write in Chinese.
- [2024-03-02] 不要用英文名词。

## PROFILE
[2024-01-15] - 我叫李雷，住在杭州。

## FACTS
- 项目 A 使用 React
2024/05/06 - Deploy waits for migrations

## PREFERENCES
[2024-02-02] - Prefer bullet points over paragraphs.
```

That is the complete list.
"""


def test_prompt_shaped_text_maps_buckets_and_dates() -> None:
    result = dry_run_pasted_memory({"text": _PROMPT_SHAPED_TEXT})

    assert result.summary.source == "pasted_memory"
    assert result.summary.status == "ready"
    assert result.summary.mapped_items == 6
    assert set(result.normalized_data) == {"procedural", "profile", "semantic"}

    procedural_contents = [item["content"] for item in result.normalized_data["procedural"]]
    assert "Always answer in Chinese when I write in Chinese." in procedural_contents
    assert "Prefer bullet points over paragraphs." in procedural_contents
    assert "不要用英文名词。" in procedural_contents

    profile_item = result.normalized_data["profile"][0]
    assert profile_item["content"] == "我叫李雷，住在杭州。"
    assert str(profile_item["created_at"]).startswith("2024-01-15")

    semantic_contents = [item["content"] for item in result.normalized_data["semantic"]]
    assert "项目 A 使用 React" in semantic_contents
    assert "Deploy waits for migrations" in semantic_contents

    # The assistant's closing sentence outside the code block must not import.
    assert all("complete list" not in content for content in procedural_contents + semantic_contents)


def test_meta_lines_and_headings_are_not_imported() -> None:
    result = dry_run_pasted_memory({"text": "## RULES\n\n- Do the thing\n"})
    contents = [item["content"] for item in result.normalized_data["procedural"]]
    assert contents == ["Do the thing"]


def test_duplicate_entries_are_imported_once() -> None:
    result = dry_run_pasted_memory(
        {"text": "- Prefers concise answers\n- prefers concise answers\n- Another fact\n"},
    )
    assert result.summary.mapped_items == 2
    assert result.summary.unmapped_items == 1
    duplicate_row = next(item for item in result.mappings if item.source_bucket == "duplicate_entries")
    assert duplicate_row.item_count == 1


def test_secrets_are_scrubbed_before_import() -> None:
    result = dry_run_pasted_memory({"text": "- My key is sk-abcdefghijklmnopqrstuvwxyz123456 for OpenAI\n"})
    contents = [item["content"] for item in result.normalized_data["semantic"]]
    assert contents
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in contents[0]
    assert "[REDACTED_API_KEY]" in contents[0]


def test_empty_payload_reports_explicit_reason() -> None:
    result = dry_run_pasted_memory({"text": "   \n\n"})
    assert result.summary.status == "missing"
    assert result.warnings == ["pasted_empty"]
    assert result.mappings[0].reason


def test_unparseable_prose_is_imported_as_facts_without_dates() -> None:
    result = dry_run_pasted_memory({"text": "Just one plain sentence about the user.\n"})
    assert result.summary.mapped_items == 1
    item = result.normalized_data["semantic"][0]
    assert item["content"] == "Just one plain sentence about the user."
    assert item["created_at"]


def test_oversized_text_is_refused_explicitly() -> None:
    result = dry_run_pasted_memory({"text": "x" * (MAX_PASTED_TEXT_CHARS + 1)})
    assert result.summary.mapped_items == 0
    assert result.warnings == ["pasted_text_too_large"]
    assert "4 MB" in result.mappings[0].reason


def test_entry_limit_is_refused_explicitly() -> None:
    text = "\n".join(f"- entry number {index}" for index in range(MAX_PASTED_ENTRIES + 1))
    result = dry_run_pasted_memory({"text": text})
    assert result.summary.mapped_items == 0
    assert result.warnings == ["pasted_entries_over_limit"]


def test_localized_headings_are_recognized() -> None:
    text = "## 指令\n- 永远使用中文回复\n\n## 個人資訊\n- 住在台中\n"
    result = dry_run_pasted_memory({"text": text})
    assert result.normalized_data["procedural"][0]["content"] == "永远使用中文回复"
    assert result.normalized_data["profile"][0]["content"] == "住在台中"


class TestModelAssistedPasteItems:
    """Model-extracted items land in the same buckets with their own keys."""

    def test_profile_items_keep_their_key_and_value(self) -> None:
        result = dry_run_pasted_model_items(
            [
                {
                    "content": "Prefers concise answers",
                    "bucket": "profile",
                    "profile_key": "tone",
                    "profile_value": "concise",
                },
                {"content": "Run tests before merge", "bucket": "procedural", "trigger": "deploy"},
                {"content": "Shipped the migration fix", "bucket": "episodic", "importance": 0.6},
            ],
        )

        profile_item = result.normalized_data["profile"][0]
        assert profile_item["key"] == "tone"
        assert profile_item["value"] == "concise"
        assert result.normalized_data["procedural"][0]["trigger_keywords"] == ["deploy"]
        assert result.normalized_data["episodic"][0]["importance"] == 0.6
        assert result.summary.mapped_items == 3

    def test_unknown_buckets_downgrade_to_semantic(self) -> None:
        result = dry_run_pasted_model_items([{"content": "Uses Postgres 17", "bucket": "unknown_kind"}])

        assert set(result.normalized_data) == {"semantic"}

    def test_extraction_failure_is_reported_on_the_result(self) -> None:
        result = dry_run_pasted_model_items([{"content": "Uses Postgres 17"}], extraction_failed=True)

        assert result.warnings == ["pasted_model_extraction_failed"]

    def test_empty_model_output_is_refused_with_a_reason(self) -> None:
        result = dry_run_pasted_model_items([])

        assert result.summary.mapped_items == 0
        assert result.warnings == ["pasted_empty"]
