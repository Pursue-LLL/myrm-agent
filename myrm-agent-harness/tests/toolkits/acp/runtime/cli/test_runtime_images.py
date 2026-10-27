"""Image files reach a CLI the way its dialect wants: Claude a readable directory, Codex ``--image=`` files."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli.runtime import CliRuntime
from myrm_agent_harness.toolkits.acp.types import RuntimeConfig, RuntimeEvent, RuntimeEventType

from ._fakes import FakeCli, make_runtime, types_of

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the CLI stand-ins are POSIX shebang scripts")


def _argv(fake_cli: FakeCli, name: str, index: int = 0) -> list[str]:
    argv = fake_cli.calls(name)[index]["argv"]
    assert isinstance(argv, list)
    return argv


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
    async def test_the_image_directory_is_on_the_command_line_of_every_turn_with_or_without_images(
        self, fake_cli: FakeCli, tmp_path: Path
    ) -> None:
        image_dir = tmp_path / "images"
        image_dir.mkdir()
        runtime = make_runtime(fake_cli, "claude", image_dir=str(image_dir))

        await _turn(runtime, "no image here")
        await _turn(runtime, "look at this", [str(image_dir / "a.png")])

        flag = f"--add-dir={image_dir}"
        first, second = _argv(fake_cli, "claude", 0), _argv(fake_cli, "claude", 1)
        assert [first.count(flag), second.count(flag)] == [1, 1]
        # The second turn is the first one plus the resume flag: the CLI's own system prompt is the same on both.
        assert second[: len(first)] == first
        assert second[len(first) :][0] == "--resume"

    @pytest.mark.asyncio
    async def test_the_prompt_is_unchanged_and_the_flag_cannot_swallow_it(
        self, fake_cli: FakeCli, tmp_path: Path
    ) -> None:
        runtime = make_runtime(fake_cli, "claude", image_dir=str(tmp_path / "images"))

        await _turn(runtime, "describe [Image: /x.png]", [str(tmp_path / "images" / "a.png")])

        assert str(fake_cli.calls("claude")[0]["prompt"]).strip() == "describe [Image: /x.png]"
        assert "--add-dir" not in _argv(fake_cli, "claude")

    @pytest.mark.asyncio
    async def test_without_an_image_directory_or_images_the_command_line_has_no_directory_flag(
        self, fake_cli: FakeCli
    ) -> None:
        await _turn(make_runtime(fake_cli, "claude"), "plain")

        assert not any(a.startswith("--add-dir") for a in _argv(fake_cli, "claude"))


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
