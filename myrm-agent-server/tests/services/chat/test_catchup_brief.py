"""Catchup brief projection: bounded previews, tool and file summaries, and the needs-from-user code."""

from __future__ import annotations

from app.services.chat.catchup_brief import (
    PROMPT_PREVIEW_MAX_CHARS,
    RESULT_PREVIEW_MAX_CHARS,
    CatchupBrief,
    extract_catchup_brief,
)
from app.services.chat.chat_helpers import WAKEUP_MESSAGE_ID_PREFIX


class TestDefaults:
    def test_empty_inputs_produce_a_safe_brief(self) -> None:
        brief = extract_catchup_brief([], [], "completed")

        assert brief == CatchupBrief()


class TestMessageExtraction:
    def test_the_last_prompt_and_latest_reply_win(self) -> None:
        messages = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
            {"role": "assistant", "content": "Done with task A"},
            {"role": "assistant", "content": "Done with task B"},
        ]

        brief = extract_catchup_brief(messages, [], "completed")

        assert brief.last_user_prompt == "Second question"
        assert brief.result_preview == "Done with task B"

    def test_empty_and_non_string_content_is_skipped(self) -> None:
        messages = [
            {"role": "user", "content": "Real question"},
            {"role": "user", "content": 123},
            {"role": "assistant", "content": "Real answer"},
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": "   "},
            {"role": "assistant", "content": None},
        ]

        brief = extract_catchup_brief(messages, [], "completed")

        assert brief.last_user_prompt == "Real question"
        assert brief.result_preview == "Real answer"

    def test_a_system_wakeup_row_is_not_the_prompt(self) -> None:
        messages = [
            {"id": "u1", "role": "user", "content": "Crawl the sites"},
            {"id": f"{WAKEUP_MESSAGE_ID_PREFIX}t1", "role": "user", "content": "<system_notification>done</system_notification>"},
        ]

        brief = extract_catchup_brief(messages, [], "completed")

        assert brief.last_user_prompt == "Crawl the sites"

    def test_previews_collapse_whitespace_and_stay_bounded(self) -> None:
        messages = [
            {"role": "user", "content": "line one\n\n   line   two " + "x" * 1000},
            {"role": "assistant", "content": "# Report\n\n" + "word " * 1000},
        ]

        brief = extract_catchup_brief(messages, [], "completed")

        assert brief.last_user_prompt.startswith("line one line two x")
        assert len(brief.last_user_prompt) == PROMPT_PREVIEW_MAX_CHARS
        assert brief.result_preview.startswith("# Report word word")
        assert RESULT_PREVIEW_MAX_CHARS - 1 <= len(brief.result_preview) <= RESULT_PREVIEW_MAX_CHARS
        assert brief.result_preview.endswith("…")
        assert "\n" not in brief.result_preview

    def test_a_short_reply_is_kept_whole(self) -> None:
        brief = extract_catchup_brief([{"role": "assistant", "content": "All done."}], [], "completed")

        assert brief.result_preview == "All done."


class TestProgressSteps:
    def test_tool_invocations_are_counted(self) -> None:
        steps = [
            {"tool_name": "file_write_tool", "items": [{"path": "a.py"}]},
            {"tool_name": "file_write_tool", "items": [{"path": "b.py"}]},
            {"tool_name": "bash_code_execute_tool", "items": [{"command": "ls"}]},
        ]

        brief = extract_catchup_brief([], steps, "completed")

        assert brief.tool_counts == {"file_write_tool": 2, "bash_code_execute_tool": 1}

    def test_only_file_mutating_tools_contribute_unique_sorted_paths(self) -> None:
        steps = [
            {"tool_name": "file_write_tool", "items": [{"path": "src/main.py"}]},
            {"tool_name": "file_edit_tool", "items": [{"path": "src/utils.py"}]},
            {"tool_name": "file_replace_tool", "items": [{"path": "src/main.py"}]},
            {"tool_name": "file_patch_tool", "items": [{"path": "tests/test.py"}]},
            {"tool_name": "file_read_tool", "items": [{"path": "README.md"}]},
        ]

        brief = extract_catchup_brief([], steps, "completed")

        assert brief.files_touched == ["src/main.py", "src/utils.py", "tests/test.py"]

    def test_malformed_tool_names_are_ignored(self) -> None:
        steps = [
            {"tool_name": "", "items": []},
            {"tool_name": None, "items": []},
            {"items": [{"path": "a.py"}]},
            {"tool_name": 123, "items": []},
        ]

        brief = extract_catchup_brief([], steps, "completed")

        assert brief.tool_counts == {}

    def test_malformed_items_are_ignored(self) -> None:
        steps = [
            {"tool_name": "file_write_tool", "items": None},
            {"tool_name": "file_write_tool", "items": "not-a-list"},
            {"tool_name": "file_write_tool", "items": [None, "string", 42, {"path": ""}, {"path": 7}]},
        ]

        brief = extract_catchup_brief([], steps, "completed")

        assert brief.files_touched == []


class TestNeedsFromUser:
    def test_a_blocked_turn_needs_approval(self) -> None:
        assert extract_catchup_brief([], [], "waiting_for_approval").needs_from_user == "approval"

    def test_a_failed_turn_needs_attention(self) -> None:
        assert extract_catchup_brief([], [], "error").needs_from_user == "error"

    def test_a_stopped_turn_needs_nothing(self) -> None:
        assert extract_catchup_brief([], [], "stopped").needs_from_user is None

    def test_a_trailing_question_mark_means_the_agent_asked(self) -> None:
        for question in ("Should I proceed with the refactor?", "要继续重构吗？", "Proceed?  \n"):
            brief = extract_catchup_brief([{"role": "assistant", "content": question}], [], "completed")
            assert brief.needs_from_user == "question", question

    def test_a_finished_reply_needs_nothing(self) -> None:
        brief = extract_catchup_brief([{"role": "assistant", "content": "All done."}], [], "completed")

        assert brief.needs_from_user is None


class TestFullScenario:
    def test_messages_and_steps_combine(self) -> None:
        messages = [
            {"role": "user", "content": "Refactor the auth module"},
            {"role": "assistant", "content": "Starting refactor..."},
            {"role": "assistant", "content": "Refactoring complete. 3 files updated."},
        ]
        steps = [
            {"tool_name": "file_edit_tool", "items": [{"path": "auth/login.py"}]},
            {"tool_name": "file_edit_tool", "items": [{"path": "auth/logout.py"}]},
            {"tool_name": "file_write_tool", "items": [{"path": "auth/middleware.py"}]},
            {"tool_name": "bash_code_execute_tool", "items": [{"command": "pytest tests/"}]},
        ]

        brief = extract_catchup_brief(messages, steps, "completed")

        assert brief.last_user_prompt == "Refactor the auth module"
        assert brief.result_preview == "Refactoring complete. 3 files updated."
        assert brief.files_touched == ["auth/login.py", "auth/logout.py", "auth/middleware.py"]
        assert brief.tool_counts == {"file_edit_tool": 2, "file_write_tool": 1, "bash_code_execute_tool": 1}
        assert brief.needs_from_user is None
        assert brief.status == "completed"
