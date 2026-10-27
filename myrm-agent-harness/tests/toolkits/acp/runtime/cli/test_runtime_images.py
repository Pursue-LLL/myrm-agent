"""Image files reach a CLI the way its dialect wants: Claude base64 blocks on stdin, Codex ``--image=`` files."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli.runtime import CliRuntime
from myrm_agent_harness.toolkits.acp.types import CliSessionRecord, RuntimeConfig, RuntimeEvent, RuntimeEventType

from ._fakes import FakeCli, RecordingStore, make_runtime, statuses_of, types_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")


def _argv(fake_cli: FakeCli, name: str, index: int = 0) -> list[str]:
    argv = fake_cli.calls(name)[index]["argv"]
    assert isinstance(argv, list)
    return argv


def _png(path: Path, body: bytes = b"pixels") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + body)
    return path


def _stdin_content(fake_cli: FakeCli, index: int = 0) -> list[dict[str, object]]:
    """The content blocks of the one stream-json user message Claude was handed on stdin."""
    message = json.loads(str(fake_cli.calls("claude")[index]["prompt"]))
    assert message["type"] == "user"
    return message["message"]["content"]


def _decoded(block: dict[str, object]) -> bytes:
    source = block["source"]
    assert isinstance(source, dict)
    return base64.b64decode(str(source["data"]))


async def _turn(runtime: CliRuntime, prompt: str, images: list[str] | None = None) -> list[RuntimeEvent]:
    return [event async for event in runtime.run_turn(prompt, "s1", images=images)]


class TestCapability:
    def test_claude_and_codex_take_images_and_other_clis_do_not(self) -> None:
        def supports(command: str) -> bool:
            return CliRuntime("t", RuntimeConfig(backend_type="cli", command=command)).capabilities.supports_images

        assert supports("claude") is True
        assert supports("/usr/local/bin/codex") is True
        assert supports("gemini") is False
        assert supports("/opt/custom/agent") is False


class TestClaude:
    @pytest.mark.asyncio
    async def test_each_image_is_a_base64_block_before_the_prompt_on_stdin(
        self, fake_cli: FakeCli, tmp_path: Path
    ) -> None:
        first = _png(tmp_path / "Application Support" / "a.png", b"first" * 100_000)
        second = _png(tmp_path / "b.png", b"second")
        runtime = make_runtime(fake_cli, "claude")

        events = await _turn(runtime, "describe [Image: /x.png]", [str(first), str(second)])

        content = _stdin_content(fake_cli)
        assert [block["type"] for block in content] == ["image", "image", "text"]
        assert [_decoded(block) for block in content[:2]] == [first.read_bytes(), second.read_bytes()]
        assert content[2] == {"type": "text", "text": "describe [Image: /x.png]"}
        argv = _argv(fake_cli, "claude")
        assert argv[argv.index("--input-format") + 1] == "stream-json"
        assert not any(a.startswith("--add-dir") or str(tmp_path) in a for a in argv)
        assert RuntimeEventType.DONE in types_of(events)

    @pytest.mark.asyncio
    async def test_a_resumed_turn_sends_its_images_too_with_the_input_format_before_the_resume_flag(
        self, fake_cli: FakeCli, tmp_path: Path
    ) -> None:
        image = _png(tmp_path / "a.png")
        runtime = make_runtime(fake_cli, "claude")

        await _turn(runtime, "first")
        events = await _turn(runtime, "second", [str(image)])

        argv = _argv(fake_cli, "claude", 1)
        assert argv.index("--input-format") < argv.index("--resume")
        assert [block["type"] for block in _stdin_content(fake_cli, 1)] == ["image", "text"]
        assert RuntimeEventType.DONE in types_of(events)

    @pytest.mark.asyncio
    async def test_a_forgotten_conversation_is_restarted_with_the_same_image_message(
        self, fake_cli: FakeCli, tmp_path: Path
    ) -> None:
        dead = "99999999-0000-4000-8000-000000000000"
        work = tmp_path / "work"
        work.mkdir()
        image = _png(tmp_path / "a.png")
        store = RecordingStore()
        store.records["s1"] = CliSessionRecord(dead, str(work))
        runtime = make_runtime(fake_cli, "claude", store=store, cwd=str(work))

        events = await _turn(runtime, "look", [str(image)])

        first, retry = _argv(fake_cli, "claude", 0), _argv(fake_cli, "claude", 1)
        assert statuses_of(events) == ["starting", "session_expired"]
        assert "--resume" in first and "--resume" not in retry
        assert "--input-format" in first and "--input-format" in retry
        assert fake_cli.calls("claude")[0]["prompt"] == fake_cli.calls("claude")[1]["prompt"]
        assert RuntimeEventType.DONE in types_of(events)

    @pytest.mark.asyncio
    async def test_a_turn_without_images_keeps_the_plain_text_prompt_and_input_format(self, fake_cli: FakeCli) -> None:
        await _turn(make_runtime(fake_cli, "claude"), "plain")

        assert str(fake_cli.calls("claude")[0]["prompt"]).strip() == "plain"
        assert "--input-format" not in _argv(fake_cli, "claude")

    @pytest.mark.asyncio
    async def test_when_no_image_can_be_read_the_turn_goes_on_as_a_plain_text_turn(
        self, fake_cli: FakeCli, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        notes = tmp_path / "notes.png"
        notes.write_text("not an image")
        runtime = make_runtime(fake_cli, "claude")

        with caplog.at_level("WARNING", logger="myrm_agent_harness.toolkits.acp.runtime.cli.image_blocks"):
            events = await _turn(runtime, "look", [str(notes), str(tmp_path / "gone.png")])

        assert str(fake_cli.calls("claude")[0]["prompt"]).strip() == "look"
        assert "--input-format" not in _argv(fake_cli, "claude")
        assert RuntimeEventType.DONE in types_of(events)
        assert len(caplog.records) == 2


class TestCodex:
    @pytest.mark.asyncio
    async def test_each_image_is_an_image_flag_and_the_prompt_stays_last(self, fake_cli: FakeCli) -> None:
        runtime = make_runtime(fake_cli, "codex")

        await _turn(runtime, "what is wrong here?", ["/img/a b.png", "/img/c.png"])

        argv = _argv(fake_cli, "codex")
        assert argv[-1] == "what is wrong here?"
        assert argv[-3:-1] == ["--image=/img/a b.png", "--image=/img/c.png"]
        assert "-i" not in argv

    @pytest.mark.asyncio
    async def test_a_resumed_turn_still_puts_the_images_before_the_session_id(self, fake_cli: FakeCli) -> None:
        runtime = make_runtime(fake_cli, "codex")

        await _turn(runtime, "first")
        events = await _turn(runtime, "second", ["/img/a.png"])

        argv = _argv(fake_cli, "codex", 1)
        thread = fake_cli.resume_args("codex")[1]
        assert thread is not None
        assert argv[argv.index("exec") + 1] == "resume"
        assert argv[-3:] == ["--image=/img/a.png", thread, "second"]
        assert RuntimeEventType.DONE in types_of(events)

    @pytest.mark.asyncio
    async def test_a_turn_without_images_has_no_image_flag(self, fake_cli: FakeCli) -> None:
        await _turn(make_runtime(fake_cli, "codex"), "plain")

        assert not any(a.startswith("--image") for a in _argv(fake_cli, "codex"))


class TestUnsupportedCli:
    @pytest.mark.asyncio
    async def test_images_for_a_cli_that_cannot_take_them_are_ignored_with_a_warning(
        self, fake_cli: FakeCli, caplog: pytest.LogCaptureFixture
    ) -> None:
        runtime = make_runtime(fake_cli, "gemini", args=[])

        with caplog.at_level("WARNING", logger="myrm_agent_harness.toolkits.acp.runtime.cli.runtime"):
            events = await _turn(runtime, "look", ["/img/a.png"])

        argv = _argv(fake_cli, "gemini")
        assert not any("a.png" in a for a in argv[:-1])
        assert RuntimeEventType.DONE in types_of(events)
        assert any("cli_runtime_images_ignored" in r.message and "images=1" in r.message for r in caplog.records)
