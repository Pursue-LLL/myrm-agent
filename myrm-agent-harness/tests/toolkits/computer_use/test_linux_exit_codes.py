"""Linux backend: failing input tools surface as errors, and text entry follows the ASCII/non-ASCII routes.

Uses real subprocesses: an empty PATH makes every tool missing, and stand-in xdotool/xclip scripts record
what the backend sends them (arguments, stdin, locale) and emulate a clipboard with genuine exit codes.
"""

from __future__ import annotations

import asyncio
import os
import stat
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.computer_use.backends import linux_text_io
from myrm_agent_harness.toolkits.computer_use.backends.linux import LinuxBackend
from myrm_agent_harness.toolkits.computer_use.types import ActionResult

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="relies on /bin/sh and POSIX PATH lookup")

# XDOTOOL_RC fails every call; XDOTOOL_FAIL_ON_CALL fails only that call number; XDOTOOL_HANG blocks typing;
# KEY_DELAY slows the paste keystroke so overlapping pastes interleave.
_FAKE_XDOTOOL = """#!/bin/sh
echo "$*" >> "$ARGV"
echo "$LC_ALL" >> "$LOCALE"
call=$(wc -l < "$ARGV" | tr -d ' ')
case "$*" in
  *--file*) [ -n "$XDOTOOL_HANG" ] && { echo $$ >> "$PIDS"; exec sleep 30; }; cat >> "$STDIN";;
  "key ctrl+v") sleep "${KEY_DELAY:-0}"; cat "$CLIPBOARD" >> "$PASTED"; echo "--" >> "$PASTED";;
  *getwindowname*) echo "Title"; echo "$DISPLAY" >> "$DISPLAY_SEEN";;
  *getmouselocation*) echo "x:7 y:9 screen:0 window:1"; echo "$DISPLAY" >> "$DISPLAY_SEEN";;
esac
[ "$call" = "$XDOTOOL_FAIL_ON_CALL" ] && exit 1
exit "${XDOTOOL_RC:-0}"
"""

# Prints a resolution only for the display the backend was told to use.
_FAKE_XDPYINFO = """#!/bin/sh
[ "$DISPLAY" = ":5" ] && echo "  dimensions:    800x600 pixels (211x159 millimeters)"
exit 0
"""

# A clipboard in a file. Reading an empty clipboard exits 1 like the real tool; XCLIP_HANG makes the read block.
_FAKE_XCLIP = """#!/bin/sh
echo "$*" >> "$XCLIP_USED"
case "$*" in
  *-o*) [ -n "$XCLIP_HANG" ] && exec sleep 30; [ -s "$CLIPBOARD" ] || exit 1; cat "$CLIPBOARD";;
  *) cat > "$CLIPBOARD";;
esac
"""

_FILES = ("argv", "stdin", "locale", "display_seen", "xclip_used", "clipboard", "pasted", "pids")


@pytest.fixture
def backend() -> LinuxBackend:
    return LinuxBackend(display_num=1)


@pytest.fixture
def empty_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))


@pytest.fixture
def fake_x_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Stand-ins for xdotool, xdpyinfo and xclip; the returned paths hold everything they recorded."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("xdotool", _FAKE_XDOTOOL), ("xdpyinfo", _FAKE_XDPYINFO), ("xclip", _FAKE_XCLIP)):
        script = bin_dir / name
        script.write_text(body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    paths = {name: tmp_path / name for name in _FILES}
    for path in paths.values():
        path.write_text("")
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    # LC_ALL outranks LC_CTYPE, so a host that pins it to a non-UTF-8 locale is the case the backend must override.
    monkeypatch.setenv("LC_ALL", "C")
    for name, path in paths.items():
        monkeypatch.setenv(name.upper(), str(path))
    return paths


_ACTIONS: dict[str, tuple[str, Callable[[LinuxBackend], Awaitable[ActionResult]]]] = {
    "type_text_ascii": ("xdotool", lambda b: b.type_text("abc")),
    "type_text_non_ascii": ("xclip", lambda b: b.type_text("你好")),
    "key": ("xdotool", lambda b: b.key("ctrl+c")),
    "mouse_move": ("xdotool", lambda b: b.mouse_move(1, 2)),
    "click": ("xdotool", lambda b: b.click(1, 2)),
    "click_with_modifier": ("xdotool", lambda b: b.click(1, 2, modifiers=["ctrl"])),
    "scroll": ("xdotool", lambda b: b.scroll(1, 2, "down")),
    "drag": ("xdotool", lambda b: b.drag(1, 2, 3, 4)),
}


class TestMissingTools:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("action", sorted(_ACTIONS))
    async def test_input_action_fails_naming_the_missing_tool(
        self, backend: LinuxBackend, empty_path: None, action: str
    ) -> None:
        tool, run = _ACTIONS[action]

        result = await run(backend)

        assert result.success is False
        assert tool in (result.error or "")


class TestDisplaySelection:
    """The display number the backend was given must reach the programs that read the screen state."""

    def test_screen_context_queries_the_selected_display(self, fake_x_tools: dict[str, Path]) -> None:
        context = LinuxBackend(display_num=5).screen_context()

        assert (context.active_window, context.mouse_x, context.mouse_y) == ("Title", 7, 9)
        assert set(fake_x_tools["display_seen"].read_text().split()) == {":5"}

    def test_resolution_is_read_from_the_selected_display(
        self, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("WIDTH", raising=False)
        monkeypatch.delenv("HEIGHT", raising=False)

        info = LinuxBackend(display_num=5).screen_info()

        assert (info.width, info.height) == (800, 600)


class TestKey:
    @pytest.mark.asyncio
    async def test_key_names_are_arguments_not_shell_code(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], tmp_path: Path
    ) -> None:
        marker = tmp_path / "injected"

        result = await backend.key(f"a; touch {marker}")

        assert result.success is True
        assert not marker.exists()
        # The whole text arrived as xdotool arguments (the fake joins argv with spaces).
        assert fake_x_tools["argv"].read_text().split("\n")[0] == f"key -- a; touch {marker}"


def _pasted(fake_x_tools: dict[str, Path]) -> list[str]:
    """What the focused application would have received for each Ctrl+V."""
    return [chunk for chunk in fake_x_tools["pasted"].read_text().split("--\n") if chunk]


class TestTypeText:
    @pytest.mark.asyncio
    async def test_ascii_goes_over_stdin_in_utf8_and_never_touches_the_clipboard(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path]
    ) -> None:
        result = await backend.type_text("hello world")

        assert result.success is True
        assert fake_x_tools["stdin"].read_text() == "hello world"
        assert fake_x_tools["argv"].read_text().split("\n")[0] == "type --delay 12 --file -"
        assert "hello world" not in fake_x_tools["argv"].read_text()
        assert set(fake_x_tools["locale"].read_text().split()) == {"C.UTF-8"}
        assert fake_x_tools["xclip_used"].read_text() == ""

    @pytest.mark.asyncio
    async def test_long_ascii_is_typed_in_chunks_and_arrives_whole(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path]
    ) -> None:
        text = "abcdefghij" * 12

        result = await backend.type_text(text)

        assert result.success is True
        assert len(fake_x_tools["argv"].read_text().splitlines()) == 3
        assert fake_x_tools["stdin"].read_text() == text

    @pytest.mark.asyncio
    async def test_failing_chunk_reports_how_far_typing_got_without_the_text(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDOTOOL_FAIL_ON_CALL", "2")
        text = "s3cret" * 20

        result = await backend.type_text(text)

        assert result.success is False
        assert "typed 50 of 120 characters" in (result.error or "")
        assert text not in (result.error or "")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("text", ["你好 world", "x" * 70 + "é", "line1\n你好\nline3"])
    async def test_any_non_ascii_text_is_pasted_whole_and_never_typed(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], text: str
    ) -> None:
        result = await backend.type_text(text)

        assert result.success is True
        assert _pasted(fake_x_tools) == [text]
        assert "type" not in fake_x_tools["argv"].read_text().split()
        assert text not in fake_x_tools["argv"].read_text()

    @pytest.mark.asyncio
    async def test_original_clipboard_comes_back_after_the_paste(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path]
    ) -> None:
        fake_x_tools["clipboard"].write_text("what the user copied")

        await backend.type_text("你好")

        assert fake_x_tools["clipboard"].read_text() == "what the user copied"

    @pytest.mark.asyncio
    async def test_empty_clipboard_is_left_empty_after_the_paste(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path]
    ) -> None:
        await backend.type_text("你好")

        assert _pasted(fake_x_tools) == ["你好"]
        assert fake_x_tools["clipboard"].read_text() == ""

    @pytest.mark.asyncio
    async def test_failed_paste_keystroke_is_reported_and_the_clipboard_still_restored(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_x_tools["clipboard"].write_text("keep me")
        monkeypatch.setenv("XDOTOOL_RC", "1")

        result = await backend.type_text("你好")

        assert result.success is False
        assert "xdotool" in (result.error or "")
        assert fake_x_tools["clipboard"].read_text() == "keep me"

    @pytest.mark.asyncio
    async def test_overlapping_pastes_each_restore_the_users_clipboard(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_x_tools["clipboard"].write_text("what the user copied")
        monkeypatch.setenv("KEY_DELAY", "1")

        first = asyncio.create_task(backend.type_text("你好"))
        # The second paste starts once the first one's text is on the clipboard: unserialized, it would save that
        # temporary text as the user's original and put it back.
        for _ in range(100):
            if fake_x_tools["clipboard"].read_text() == "你好":
                break
            await asyncio.sleep(0.05)
        second = await backend.type_text("世界")

        assert (await first).success and second.success
        assert sorted(_pasted(fake_x_tools)) == ["世界", "你好"]
        assert fake_x_tools["clipboard"].read_text() == "what the user copied"

    @pytest.mark.asyncio
    async def test_stuck_clipboard_owner_does_not_stall_the_paste(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(linux_text_io, "_CLIPBOARD_READ_TIMEOUT_S", 0.3)
        monkeypatch.setenv("XCLIP_HANG", "1")

        result = await asyncio.wait_for(backend.type_text("你好"), 5)

        assert result.success is True
        assert _pasted(fake_x_tools) == ["你好"]

    @pytest.mark.asyncio
    async def test_cancelled_typing_kills_the_running_xdotool(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # asyncio kills a still-running child when its Process object is garbage-collected; keeping the objects
        # alive leaves the explicit kill as the only thing that can stop it.
        spawned: list[asyncio.subprocess.Process] = []
        spawn = asyncio.create_subprocess_exec

        async def keep_alive(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
            proc = await spawn(*args, **kwargs)  # type: ignore[arg-type]
            spawned.append(proc)
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", keep_alive)
        monkeypatch.setenv("XDOTOOL_HANG", "1")
        task = asyncio.create_task(backend.type_text("abc"))
        for _ in range(100):
            if fake_x_tools["pids"].read_text().strip():
                break
            await asyncio.sleep(0.05)
        pid = int(fake_x_tools["pids"].read_text().split()[0])

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        for _ in range(100):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            await asyncio.sleep(0.05)
        pytest.fail("xdotool kept running after its caller was cancelled")


class _Vault:
    """Stands in for the CredentialVault: hands out one fixed secret."""

    def __init__(self, secret: str) -> None:
        self._secret = secret

    def get_password(self, _label: str) -> str:
        return self._secret

    def get_totp_token(self, _label: str) -> str:
        return self._secret


@pytest.fixture
def vault_secret(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    def install(secret: str) -> None:
        monkeypatch.setattr(
            "myrm_agent_harness.core.security.credential_vault.get_global_credential_vault", lambda: _Vault(secret)
        )

    return install


class TestTypeCredential:
    _SECRET = "S3cr3t-Pw"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label", ["bank", "bank-totp"])
    async def test_ascii_secret_reaches_stdin_and_never_the_command_line(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], vault_secret: Callable[[str], None], label: str
    ) -> None:
        vault_secret(self._SECRET)

        result = await backend.type_credential(label)

        assert result.success is True
        assert fake_x_tools["stdin"].read_text() == self._SECRET
        assert fake_x_tools["argv"].read_text().split("\n")[0] == "type --delay 12 --file -"
        assert self._SECRET not in fake_x_tools["argv"].read_text()

    @pytest.mark.asyncio
    async def test_failing_xdotool_is_reported_without_the_secret(
        self,
        backend: LinuxBackend,
        fake_x_tools: dict[str, Path],
        vault_secret: Callable[[str], None],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        vault_secret(self._SECRET)
        monkeypatch.setenv("XDOTOOL_RC", "1")

        result = await backend.type_credential("bank")

        assert result.success is False
        assert "xdotool" in (result.error or "")
        assert self._SECRET not in (result.error or "")

    @pytest.mark.asyncio
    async def test_non_ascii_secret_is_pasted_never_on_the_command_line_and_the_clipboard_is_restored(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], vault_secret: Callable[[str], None]
    ) -> None:
        vault_secret("密码-S3cr3t")
        fake_x_tools["clipboard"].write_text("what the user copied")

        result = await backend.type_credential("bank")

        assert result.success is True
        assert _pasted(fake_x_tools) == ["密码-S3cr3t"]
        assert "密码" not in fake_x_tools["argv"].read_text()
        assert fake_x_tools["clipboard"].read_text() == "what the user copied"
