"""Linux backend must surface failing xdotool invocations instead of reporting success.

Uses real subprocesses: an empty PATH makes the shell return 127 for every tool, and a fake
xdotool script records what the backend sends it (arguments, stdin, locale) with genuine exit codes.
"""

from __future__ import annotations

import stat
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.computer_use.backends.linux import LinuxBackend
from myrm_agent_harness.toolkits.computer_use.types import ActionResult

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="relies on /bin/sh and POSIX PATH lookup")

_FAKE_XDOTOOL = """#!/bin/sh
echo "$*" >> "$ARGV"
echo "$LC_CTYPE" >> "$LOCALE"
case "$*" in
  *--file*) cat >> "$STDIN";;
  *getwindowname*) echo "Title"; echo "$DISPLAY" >> "$DISPLAY_SEEN";;
  *getmouselocation*) echo "x:7 y:9 screen:0 window:1"; echo "$DISPLAY" >> "$DISPLAY_SEEN";;
esac
exit "${XDOTOOL_RC:-0}"
"""

# Prints a resolution only for the display the backend was told to use.
_FAKE_XDPYINFO = """#!/bin/sh
[ "$DISPLAY" = ":5" ] && echo "  dimensions:    800x600 pixels (211x159 millimeters)"
exit 0
"""

# A clipboard tool the backend must never reach for: any call is recorded.
_TRIPWIRE_XCLIP = """#!/bin/sh
echo "$*" >> "$XCLIP_USED"
"""


@pytest.fixture
def backend() -> LinuxBackend:
    return LinuxBackend(display_num=1)


@pytest.fixture
def empty_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))


@pytest.fixture
def fake_x_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """xdotool stand-in: argv/stdin/locale record what it received; xclip_used records any clipboard-tool call."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("xdotool", _FAKE_XDOTOOL), ("xdpyinfo", _FAKE_XDPYINFO), ("xclip", _TRIPWIRE_XCLIP)):
        script = bin_dir / name
        script.write_text(body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    paths = {name: tmp_path / name for name in ("argv", "stdin", "locale", "display_seen", "xclip_used")}
    for path in paths.values():
        path.write_text("")
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    for name, path in paths.items():
        monkeypatch.setenv(name.upper(), str(path))
    return paths


_ACTIONS: dict[str, Callable[[LinuxBackend], Awaitable[ActionResult]]] = {
    "type_text_ascii": lambda b: b.type_text("abc"),
    "type_text_non_ascii": lambda b: b.type_text("你好"),
    "key": lambda b: b.key("ctrl+c"),
    "mouse_move": lambda b: b.mouse_move(1, 2),
    "click": lambda b: b.click(1, 2),
    "click_with_modifier": lambda b: b.click(1, 2, modifiers=["ctrl"]),
    "scroll": lambda b: b.scroll(1, 2, "down"),
    "drag": lambda b: b.drag(1, 2, 3, 4),
}


class TestMissingTools:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("action", sorted(_ACTIONS))
    async def test_input_action_fails_when_xdotool_is_missing(
        self, backend: LinuxBackend, empty_path: None, action: str
    ) -> None:
        result = await _ACTIONS[action](backend)

        assert result.success is False
        assert "xdotool" in (result.error or "")


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


class TestTypeText:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("text", ["hello world", "你好 world"])
    async def test_text_reaches_xdotool_over_stdin_in_utf8_and_never_touches_the_clipboard(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], text: str
    ) -> None:
        result = await backend.type_text(text)

        assert result.success is True
        assert fake_x_tools["stdin"].read_text() == text
        assert fake_x_tools["argv"].read_text().split("\n")[0] == "type --delay 12 --file -"
        assert text not in fake_x_tools["argv"].read_text()
        # xdotool decodes the bytes with the locale it runs under; anything but UTF-8 stops it mid-text.
        assert set(fake_x_tools["locale"].read_text().split()) == {"C.UTF-8"}
        assert fake_x_tools["xclip_used"].read_text() == ""

    @pytest.mark.asyncio
    async def test_long_text_is_typed_in_chunks_and_arrives_whole(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path]
    ) -> None:
        text = "你好世界" * 30

        result = await backend.type_text(text)

        assert result.success is True
        assert len(fake_x_tools["argv"].read_text().splitlines()) == 3
        assert fake_x_tools["stdin"].read_text() == text

    @pytest.mark.asyncio
    async def test_failing_xdotool_is_reported_for_non_ascii_text(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDOTOOL_RC", "1")

        result = await backend.type_text("你好")

        assert result.success is False
        assert "xdotool" in (result.error or "")


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
    async def test_non_ascii_secret_reaches_stdin_and_never_the_command_line_or_the_clipboard(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], vault_secret: Callable[[str], None]
    ) -> None:
        vault_secret("密码-S3cr3t")

        result = await backend.type_credential("bank")

        assert result.success is True
        assert fake_x_tools["stdin"].read_text() == "密码-S3cr3t"
        assert "密码" not in fake_x_tools["argv"].read_text()
        assert set(fake_x_tools["locale"].read_text().split()) == {"C.UTF-8"}
        assert fake_x_tools["xclip_used"].read_text() == ""
