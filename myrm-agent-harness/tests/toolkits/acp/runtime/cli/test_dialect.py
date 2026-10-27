"""Per-CLI dialects: how Claude and Codex are told to resume a conversation, limit turns and stream text."""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli.dialect import (
    CliDialect,
    dialect_for,
    has_native_turn_limit,
    is_session_id,
)
from myrm_agent_harness.toolkits.acp.runtime.cli.image_blocks import ImageBlock

_ID = "0198a7c3-5d2e-7c41-9b8e-1f2a3b4c5d6e"
_BLOCK = ImageBlock("image/png", "AAEC")
_BLOCK_JPEG = ImageBlock("image/jpeg", "/9j/")


class TestSessionId:
    def test_a_canonical_uuid_is_a_session_id(self) -> None:
        assert is_session_id(_ID)
        assert is_session_id(_ID.upper())

    @pytest.mark.parametrize(
        "value",
        ["", "abc", "deadbeef", _ID + "0", " " + _ID, _ID.replace("-", ""), "--help", "-x " + _ID, _ID + "\n--flag"],
    )
    def test_anything_else_is_never_replayed_to_a_cli(self, value: str) -> None:
        assert not is_session_id(value)


class TestDialectLookup:
    @pytest.mark.parametrize("command", ["claude", "/usr/local/bin/claude", "claude-code", "codex", "/opt/bin/codex"])
    def test_claude_and_codex_commands_have_a_dialect(self, command: str) -> None:
        assert dialect_for(command) is not None

    @pytest.mark.parametrize("command", ["gemini", "qwen", "/opt/custom/agent", "", None])
    def test_other_commands_do_not(self, command: str | None) -> None:
        assert dialect_for(command) is None

    def test_only_claude_has_a_native_turn_limit(self) -> None:
        assert has_native_turn_limit("claude")
        assert has_native_turn_limit("/usr/local/bin/claude")
        assert not has_native_turn_limit("codex")
        assert not has_native_turn_limit("gemini")
        assert not has_native_turn_limit(None)


class TestClaudeDialect:
    def test_resume_is_a_trailing_flag(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None

        assert dialect.with_resume(["claude", "-p"], _ID) == ["claude", "-p", "--resume", _ID]

    def test_a_malformed_id_cannot_carry_a_resume(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None

        assert dialect.with_resume(["claude", "-p"], "--dangerous") is None

    def test_configured_resume_args_are_left_alone(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None

        assert dialect.is_resuming(["claude", "--resume", "x"])
        assert not dialect.is_resuming(["claude", "-p"])

    def test_the_turn_limit_is_added_once_and_only_when_positive(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None

        assert dialect.with_max_turns(["claude"], 7) == ["claude", "--max-turns", "7"]
        assert dialect.with_max_turns(["claude"], 0) == ["claude"]
        assert dialect.with_max_turns(["claude", "--max-turns", "3"], 7) == ["claude", "--max-turns", "3"]

    def test_partial_messages_are_asked_for_only_in_stream_json(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None

        streaming = ["claude", "--output-format", "stream-json"]
        assert dialect.with_partial_messages(streaming) == [*streaming, "--include-partial-messages"]
        assert dialect.with_partial_messages([*streaming, "--include-partial-messages"]) == [
            *streaming,
            "--include-partial-messages",
        ]
        assert dialect.with_partial_messages(["claude", "--output-format", "json"]) == [
            "claude",
            "--output-format",
            "json",
        ]


class TestCodexDialect:
    def test_resume_is_a_subcommand_that_takes_the_id_before_the_prompt(self) -> None:
        dialect = dialect_for("codex")
        assert dialect is not None
        args = ["codex", "--sandbox", "workspace-write", "exec", "--json", "--skip-git-repo-check"]

        assert dialect.with_resume(args, _ID) == [
            "codex",
            "--sandbox",
            "workspace-write",
            "exec",
            "resume",
            "--json",
            "--skip-git-repo-check",
            _ID,
        ]

    def test_without_an_exec_subcommand_nothing_can_resume(self) -> None:
        dialect = dialect_for("codex")
        assert dialect is not None

        assert dialect.with_resume(["codex", "--json"], _ID) is None

    def test_a_malformed_id_is_refused_because_codex_would_silently_start_a_new_thread(self) -> None:
        dialect = dialect_for("codex")
        assert dialect is not None

        assert dialect.with_resume(["codex", "exec", "--json"], "not-a-uuid") is None

    def test_configured_resume_is_detected_after_exec_only(self) -> None:
        dialect = dialect_for("codex")
        assert dialect is not None

        assert dialect.is_resuming(["codex", "exec", "resume", "--json"])
        assert not dialect.is_resuming(["codex", "exec", "--json"])
        assert not dialect.is_resuming(["codex", "resume"])

    def test_codex_has_no_turn_limit_or_partial_message_flag(self) -> None:
        dialect = dialect_for("codex")
        assert dialect is not None
        args = ["codex", "exec", "--json", "stream-json"]

        assert dialect.with_max_turns(args, 7) == args
        assert dialect.with_partial_messages(args) == args


class TestEnvDefaults:
    def test_claude_runs_headless_without_background_tasks(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None

        assert dict(dialect.env_defaults) == {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}

    def test_codex_needs_no_environment(self) -> None:
        dialect = dialect_for("codex")
        assert dialect is not None

        assert not dialect.env_defaults


class TestImages:
    def test_a_cli_without_a_dialect_class_for_images_takes_none(self) -> None:
        args = ["gemini", "--output-format", "stream-json"]

        assert CliDialect.takes_images is False
        assert CliDialect.sends_image_blocks is False
        assert CliDialect().with_images(args, ["/img/a.png"]) == args
        assert CliDialect().with_image_blocks(args, "look", [_BLOCK]) == (args, "look")

    def test_claude_sends_the_images_and_the_prompt_as_one_stream_json_user_message(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None
        args = ["claude", "-p", "--output-format", "stream-json"]

        new_args, stdin = dialect.with_image_blocks(args, "what is wrong?", [_BLOCK, _BLOCK_JPEG])

        assert dialect.takes_images and dialect.sends_image_blocks
        assert new_args == [*args, "--input-format", "stream-json"]
        assert "\n" not in stdin
        assert json.loads(stdin) == {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAEC"}},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "/9j/"}},
                    {"type": "text", "text": "what is wrong?"},
                ],
            },
        }

    def test_a_prompt_with_newlines_and_non_ascii_text_stays_one_line_and_survives_intact(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None
        prompt = '第一行\n"quoted" \\ [Image: /Users/张 三/a.png]\r\n'

        _, stdin = dialect.with_image_blocks(["claude", "-p"], prompt, [_BLOCK])

        assert "\n" not in stdin
        assert json.loads(stdin)["message"]["content"][-1] == {"type": "text", "text": prompt}

    @pytest.mark.parametrize("prompt", ["", "  \n"])
    def test_a_blank_prompt_sends_the_images_alone(self, prompt: str) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None

        _, stdin = dialect.with_image_blocks(["claude", "-p"], prompt, [_BLOCK])

        assert [block["type"] for block in json.loads(stdin)["message"]["content"]] == ["image"]

    def test_claude_without_blocks_keeps_a_plain_text_turn(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None
        args = ["claude", "-p"]

        assert dialect.with_image_blocks(args, "look  ", []) == (args, "look  ")
        assert dialect.with_images(args, ["/a.png"]) == args

    def test_an_input_format_the_args_already_hold_is_not_repeated(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None
        args = ["claude", "-p", "--input-format", "stream-json"]

        new_args, _ = dialect.with_image_blocks(args, "look", [_BLOCK])

        assert new_args == args

    def test_a_resumed_claude_turn_keeps_the_input_format_before_the_resume_flag(self) -> None:
        dialect = dialect_for("claude")
        assert dialect is not None

        args, _ = dialect.with_image_blocks(["claude", "-p"], "look", [_BLOCK])

        assert dialect.with_resume(args, _ID) == ["claude", "-p", "--input-format", "stream-json", "--resume", _ID]

    def test_codex_attaches_each_image_as_an_image_flag_in_the_equals_form(self) -> None:
        dialect = dialect_for("codex")
        assert dialect is not None
        args = ["codex", "exec", "--json"]

        assert dialect.takes_images and not dialect.sends_image_blocks
        assert dialect.with_images(args, ["/a b.png", "/c.png"]) == [*args, "--image=/a b.png", "--image=/c.png"]
        assert dialect.with_images(args, []) == args
        assert dialect.with_image_blocks(args, "look", [_BLOCK]) == (args, "look")

    def test_a_resumed_codex_turn_keeps_the_images_before_the_session_id_and_the_prompt(self) -> None:
        dialect = dialect_for("codex")
        assert dialect is not None
        base = ["codex", "exec", "--json", "--skip-git-repo-check"]

        resumed = dialect.with_resume(dialect.with_images(base, ["/a.png"]), _ID)

        assert resumed == ["codex", "exec", "resume", "--json", "--skip-git-repo-check", "--image=/a.png", _ID]
