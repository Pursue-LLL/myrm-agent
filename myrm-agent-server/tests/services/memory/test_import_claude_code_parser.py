"""Tests for Claude Code JSONL transcript parser and adapter integration.

Covers: dedup, entry classification, conversation turn reconstruction,
three-bucket mapping, data limit caps, warning generation, auto-detection,
and full dry-run adapter pipeline.
"""

from __future__ import annotations

from app.services.memory.import_adapters import build_memory_import_dry_run
from app.services.memory.import_claude_code_parser import (
    MAX_CLAUDE_CODE_ENTRIES,
    MAX_CLAUDE_CODE_LINES,
    MAX_ERRORS_FOR_PROCEDURAL,
    MAX_SUMMARIES_FOR_SEMANTIC,
    MAX_TURNS_FOR_EPISODIC,
    WARNING_NO_CONVERSATION_ENTRIES,
    WARNING_TOO_MANY_ENTRIES,
    WARNING_TOO_MANY_LINES,
    ConversationTurn,
    errors_to_procedural,
    parse_claude_code_lines,
    summaries_to_semantic,
    turns_to_episodic,
)


def _user(uid: str, content: str) -> dict[str, object]:
    return {"type": "user", "id": uid, "message": {"role": "user", "content": content}}


def _assistant(aid: str, text: str, tools: list[dict[str, object]] | None = None) -> dict[str, object]:
    blocks: list[dict[str, object]] = [{"type": "text", "text": text}]
    if tools:
        blocks.extend(tools)
    return {"type": "assistant", "id": aid, "message": {"role": "assistant", "content": blocks}}


def _tool_use(name: str) -> dict[str, object]:
    return {"type": "tool_use", "name": name, "id": f"tool_{name}", "input": {}}


def _summary(sid: str, text: str) -> dict[str, object]:
    return {"type": "summary", "id": sid, "summary": text}


def _system_error(eid: str, error_text: str) -> dict[str, object]:
    return {"type": "system", "id": eid, "subtype": "api_error", "error": error_text}


def _system_normal(sid: str) -> dict[str, object]:
    return {"type": "system", "id": sid, "subtype": "info"}


class TestParseClaudeCodeLines:
    def test_basic_parsing(self) -> None:
        lines: list[object] = [
            _user("u1", "Fix bug"),
            _assistant("a1", "Done", [_tool_use("EditFile")]),
        ]
        result = parse_claude_code_lines(lines)
        assert result.total_lines == 2
        assert result.deduplicated_entries == 2
        assert result.user_entries == 1
        assert result.assistant_entries == 1
        assert result.summary_entries == 0
        assert result.system_entries == 0
        assert result.skipped_entries == 0
        assert len(result.turns) == 1
        assert result.turns[0].user_content == "Fix bug"
        assert result.turns[0].assistant_content == "Done"
        assert result.turns[0].tool_names == ["EditFile"]

    def test_dedup_last_write_wins(self) -> None:
        lines: list[object] = [
            _user("u1", "Original question"),
            _user("u1", "Updated question"),
        ]
        result = parse_claude_code_lines(lines)
        assert result.deduplicated_entries == 1
        assert result.user_entries == 1
        assert result.turns[0].user_content == "Updated question"

    def test_entries_without_id_not_deduped(self) -> None:
        lines: list[object] = [
            {"type": "user", "message": {"role": "user", "content": "msg1"}},
            {"type": "user", "message": {"role": "user", "content": "msg2"}},
        ]
        result = parse_claude_code_lines(lines)
        assert result.deduplicated_entries == 2
        assert result.user_entries == 2

    def test_summary_entries(self) -> None:
        lines: list[object] = [
            _summary("s1", "Project architecture overview"),
            _summary("s2", "Database schema design"),
        ]
        result = parse_claude_code_lines(lines)
        assert result.summary_entries == 2
        assert len(result.summaries) == 2

    def test_system_error_entries(self) -> None:
        lines: list[object] = [
            _system_error("e1", "Rate limit exceeded"),
            _system_normal("n1"),
        ]
        result = parse_claude_code_lines(lines)
        assert result.system_entries == 2
        assert len(result.errors) == 1

    def test_skipped_entry_types(self) -> None:
        lines: list[object] = [
            {"type": "file-history-snapshot", "id": "f1"},
            {"type": "pr-link", "id": "p1"},
            {"type": "progress", "id": "pr1"},
            {"type": "queue-operation", "id": "q1"},
            {"type": "saved_hook_context", "id": "h1"},
            {"type": "unknown_type", "id": "x1"},
        ]
        result = parse_claude_code_lines(lines)
        assert result.skipped_entries == 6
        assert result.user_entries == 0
        assert result.assistant_entries == 0

    def test_non_dict_entries_skipped(self) -> None:
        lines: list[object] = [
            "just a string",
            42,
            None,
            _user("u1", "valid"),
        ]
        result = parse_claude_code_lines(lines)
        assert result.deduplicated_entries == 1
        assert result.user_entries == 1

    def test_empty_input(self) -> None:
        result = parse_claude_code_lines([])
        assert result.total_lines == 0
        assert result.deduplicated_entries == 0
        assert WARNING_NO_CONVERSATION_ENTRIES in result.warnings

    def test_no_conversation_warning(self) -> None:
        lines: list[object] = [_summary("s1", "Summary only")]
        result = parse_claude_code_lines(lines)
        assert WARNING_NO_CONVERSATION_ENTRIES in result.warnings

    def test_too_many_lines_warning(self) -> None:
        lines: list[object] = [_user(f"u{i}", f"msg{i}") for i in range(MAX_CLAUDE_CODE_LINES + 10)]
        result = parse_claude_code_lines(lines)
        assert WARNING_TOO_MANY_LINES in result.warnings

    def test_too_many_entries_warning(self) -> None:
        lines: list[object] = [
            {"type": "user", "message": {"role": "user", "content": f"m{i}"}} for i in range(MAX_CLAUDE_CODE_ENTRIES + 10)
        ]
        result = parse_claude_code_lines(lines)
        assert WARNING_TOO_MANY_ENTRIES in result.warnings

    def test_turn_pairing_multiple(self) -> None:
        lines: list[object] = [
            _user("u1", "Q1"),
            _assistant("a1", "A1"),
            _user("u2", "Q2"),
            _assistant("a2", "A2"),
            _user("u3", "Q3"),
        ]
        result = parse_claude_code_lines(lines)
        assert len(result.turns) == 3
        assert result.turns[0].user_content == "Q1"
        assert result.turns[0].assistant_content == "A1"
        assert result.turns[2].user_content == "Q3"
        assert result.turns[2].assistant_content == ""

    def test_multipart_content(self) -> None:
        entry: dict[str, object] = {
            "type": "assistant",
            "id": "a1",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Part 1"},
                    {"type": "text", "text": "Part 2"},
                    {"type": "tool_use", "name": "Bash", "id": "t1", "input": {}},
                ],
            },
        }
        lines: list[object] = [_user("u1", "Go"), entry]
        result = parse_claude_code_lines(lines)
        assert result.turns[0].assistant_content == "Part 1\nPart 2"
        assert result.turns[0].tool_names == ["Bash"]

    def test_content_as_string(self) -> None:
        entry: dict[str, object] = {
            "type": "assistant",
            "id": "a1",
            "message": {"role": "assistant", "content": "Simple string response"},
        }
        lines: list[object] = [_user("u1", "Q"), entry]
        result = parse_claude_code_lines(lines)
        assert result.turns[0].assistant_content == "Simple string response"

    def test_fallback_content_field(self) -> None:
        entry: dict[str, object] = {"type": "user", "id": "u1", "content": "Fallback content"}
        lines: list[object] = [entry]
        result = parse_claude_code_lines(lines)
        assert result.turns[0].user_content == "Fallback content"


class TestTurnsToEpisodic:
    def test_basic_mapping(self) -> None:
        turns = [
            ConversationTurn(
                user_content="Fix the bug",
                assistant_content="I fixed it",
                tool_names=["EditFile", "Bash"],
                timestamp="2024-01-01T00:00:00Z",
            )
        ]
        result = turns_to_episodic(turns)
        assert len(result) == 1
        entry = result[0]
        assert "User: Fix the bug" in entry["content"]
        assert "Tools: EditFile, Bash" in entry["content"]
        assert "Assistant: I fixed it" in entry["content"]
        assert entry["event_type"] == "claude_code_conversation_turn"
        assert entry["metadata"]["external_source"] == "claude_code_jsonl"
        assert entry["metadata"]["tool_count"] == 2
        assert entry["importance"] == 0.5
        assert entry["related_entities"] == ["EditFile", "Bash"]

    def test_content_truncation(self) -> None:
        turns = [ConversationTurn(user_content="x" * 2000, assistant_content="y" * 2000)]
        result = turns_to_episodic(turns)
        content = str(result[0]["content"])
        assert len(content) < 2000

    def test_cap_at_max_turns(self) -> None:
        turns = [ConversationTurn(user_content=f"q{i}", assistant_content=f"a{i}") for i in range(MAX_TURNS_FOR_EPISODIC + 50)]
        result = turns_to_episodic(turns)
        assert len(result) == MAX_TURNS_FOR_EPISODIC

    def test_no_tools_omitted(self) -> None:
        turns = [ConversationTurn(user_content="Hi", assistant_content="Hello")]
        result = turns_to_episodic(turns)
        assert "Tools:" not in str(result[0]["content"])


class TestSummariesToSemantic:
    def test_basic_mapping(self) -> None:
        summaries: list[dict[str, object]] = [{"summary": "Project uses React and TypeScript"}]
        result = summaries_to_semantic(summaries)
        assert len(result) == 1
        assert "React and TypeScript" in result[0]["content"]
        assert result[0]["importance"] == 0.75
        assert result[0]["metadata"]["external_source"] == "claude_code_jsonl"

    def test_empty_summary_skipped(self) -> None:
        summaries: list[dict[str, object]] = [{"summary": ""}, {"summary": "Valid"}]
        result = summaries_to_semantic(summaries)
        assert len(result) == 1

    def test_cap_at_max(self) -> None:
        summaries: list[dict[str, object]] = [{"summary": f"s{i}"} for i in range(MAX_SUMMARIES_FOR_SEMANTIC + 50)]
        result = summaries_to_semantic(summaries)
        assert len(result) == MAX_SUMMARIES_FOR_SEMANTIC

    def test_message_content_fallback(self) -> None:
        summaries: list[dict[str, object]] = [{"message": {"content": "Via message field"}}]
        result = summaries_to_semantic(summaries)
        assert len(result) == 1
        assert "Via message field" in result[0]["content"]


class TestErrorsToProcedural:
    def test_basic_mapping(self) -> None:
        errors: list[dict[str, object]] = [{"error": "Rate limit exceeded"}]
        result = errors_to_procedural(errors)
        assert len(result) == 1
        assert "Rate limit" in result[0]["content"]
        assert result[0]["priority"] == 5
        assert result[0]["metadata"]["external_source"] == "claude_code_jsonl"

    def test_empty_error_skipped(self) -> None:
        errors: list[dict[str, object]] = [{"error": ""}, {"error": "Real error"}]
        result = errors_to_procedural(errors)
        assert len(result) == 1

    def test_cap_at_max(self) -> None:
        errors: list[dict[str, object]] = [{"error": f"e{i}"} for i in range(MAX_ERRORS_FOR_PROCEDURAL + 50)]
        result = errors_to_procedural(errors)
        assert len(result) == MAX_ERRORS_FOR_PROCEDURAL

    def test_message_fallback(self) -> None:
        errors: list[dict[str, object]] = [{"message": "Error via message field"}]
        result = errors_to_procedural(errors)
        assert len(result) == 1


class TestDryRunClaudeCodeJsonl:
    def test_full_pipeline(self) -> None:
        payload: dict[str, object] = {
            "jsonl_lines": [
                _user("u1", "Fix auth"),
                _assistant("a1", "Fixed", [_tool_use("EditFile")]),
                _summary("s1", "Auth module overview"),
                _system_error("e1", "API rate limited"),
            ]
        }
        result = build_memory_import_dry_run(payload, "claude_code_jsonl")
        assert result.summary.source == "claude_code_jsonl"
        assert result.summary.mapped_items == 3
        assert result.summary.status in ("ready", "warning")
        assert len(result.mappings) == 3
        bucket_names = {m.source_bucket for m in result.mappings}
        assert bucket_names == {"conversation_turns", "summaries", "system_errors"}

    def test_auto_detection(self) -> None:
        payload: dict[str, object] = {"jsonl_lines": [_user("u1", "Hello"), _assistant("a1", "Hi")]}
        result = build_memory_import_dry_run(payload, "auto")
        assert result.summary.source == "claude_code_jsonl"

    def test_empty_lines(self) -> None:
        payload: dict[str, object] = {"jsonl_lines": []}
        result = build_memory_import_dry_run(payload, "claude_code_jsonl")
        assert "claude_code_no_lines" in result.warnings

    def test_conversation_only(self) -> None:
        payload: dict[str, object] = {"jsonl_lines": [_user("u1", "Q"), _assistant("a1", "A")]}
        result = build_memory_import_dry_run(payload, "claude_code_jsonl")
        assert result.summary.mapped_items == 1
        episodic_mapping = next(m for m in result.mappings if m.target_bucket == "episodic")
        assert episodic_mapping.status == "mapped"
        assert episodic_mapping.imported_count == 1

    def test_summary_only(self) -> None:
        payload: dict[str, object] = {"jsonl_lines": [_summary("s1", "Project overview")]}
        result = build_memory_import_dry_run(payload, "claude_code_jsonl")
        assert result.summary.mapped_items == 1
        semantic_mapping = next(m for m in result.mappings if m.target_bucket == "semantic")
        assert semantic_mapping.status == "mapped"

    def test_normalized_data_structure(self) -> None:
        payload: dict[str, object] = {
            "jsonl_lines": [
                _user("u1", "Q"),
                _assistant("a1", "A"),
                _summary("s1", "Summary"),
                _system_error("e1", "Error"),
            ]
        }
        result = build_memory_import_dry_run(payload, "claude_code_jsonl")
        assert "episodic" in result.normalized_data
        assert "semantic" in result.normalized_data
        assert "procedural" in result.normalized_data
        assert len(result.normalized_data["episodic"]) == 1
        assert len(result.normalized_data["semantic"]) == 1
        assert len(result.normalized_data["procedural"]) == 1

    def test_dedup_in_pipeline(self) -> None:
        payload: dict[str, object] = {
            "jsonl_lines": [
                _user("u1", "Original"),
                _user("u1", "Corrected"),
                _assistant("a1", "Response"),
            ]
        }
        result = build_memory_import_dry_run(payload, "claude_code_jsonl")
        episodic = result.normalized_data.get("episodic", [])
        assert len(episodic) == 1
        assert "Corrected" in str(episodic[0].get("content", ""))
