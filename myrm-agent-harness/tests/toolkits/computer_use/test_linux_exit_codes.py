"""Linux backend must surface failing xdotool/xclip invocations instead of reporting success.

Uses real subprocesses: an empty PATH makes the shell return 127 for every tool, and
fake xclip/xdotool scripts exercise the clipboard restore with genuine exit codes.
"""

from __future__ import annotations

import asyncio
import os
import stat
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import psutil
import pytest

from myrm_agent_harness.toolkits.computer_use.backends import linux as linux_module
from myrm_agent_harness.toolkits.computer_use.backends.linux import LinuxBackend
from myrm_agent_harness.toolkits.computer_use.types import ActionResult

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="relies on /bin/sh and POSIX PATH lookup")

_FAKE_XCLIP = """#!/bin/sh
case "$*" in *-o*)
    # XCLIP_HANG is the (unique) duration of the stuck read; exec makes the sleep the very process a kill must reach.
    if [ -n "$XCLIP_HANG" ]; then exec sleep "$XCLIP_HANG"; fi
    cat "$CLIP"; exit 0;;
esac
cat > "$CLIP"
"""

_FAKE_XDOTOOL = """#!/bin/sh
echo "$*" >> "$ARGV"
case "$*" in *--file*) cat >> "$STDIN";; esac
if [ "$1" = key ]; then touch "$ENTERED"; cat "$CLIP" >> "$SEEN"; sleep "${XDOTOOL_DELAY:-0}"; fi
exit "${XDOTOOL_RC:-0}"
"""


@pytest.fixture
def backend() -> LinuxBackend:
    return LinuxBackend(display_num=1)


@pytest.fixture
def empty_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))


@pytest.fixture
def fake_x_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """xclip/xdotool stand-ins: clip is the clipboard, seen what Ctrl+V would paste, argv/stdin what xdotool received.

    `entered` appears once a Ctrl+V keystroke is being sent; XDOTOOL_DELAY stretches that keystroke.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("xclip", _FAKE_XCLIP), ("xdotool", _FAKE_XDOTOOL)):
        script = bin_dir / name
        script.write_text(body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    paths = {name: tmp_path / name for name in ("clip", "seen", "argv", "stdin", "entered")}
    paths["clip"].write_text("old")
    for name in ("seen", "argv", "stdin"):
        paths[name].write_text("")
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    for name, path in paths.items():
        monkeypatch.setenv(name.upper(), str(path))
    return paths


_ACTIONS: dict[str, Callable[[LinuxBackend], Awaitable[ActionResult]]] = {
    "type_text_ascii": lambda b: b.type_text("abc"),
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

    @pytest.mark.asyncio
    async def test_non_ascii_text_fails_when_xclip_is_missing(self, backend: LinuxBackend, empty_path: None) -> None:
        result = await backend.type_text("你好")

        assert result.success is False
        assert "xclip" in (result.error or "")


class TestClipboardPaste:
    @pytest.mark.asyncio
    async def test_target_sees_the_text_and_the_clipboard_comes_back(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path]
    ) -> None:
        result = await backend.type_text("你好")

        assert result.success is True
        assert fake_x_tools["seen"].read_text() == "你好"
        assert fake_x_tools["clip"].read_text() == "old"

    @pytest.mark.asyncio
    async def test_failed_paste_keystroke_is_reported_and_the_clipboard_still_comes_back(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDOTOOL_RC", "1")

        result = await backend.type_text("你好")

        assert result.success is False
        assert "xdotool" in (result.error or "")
        assert fake_x_tools["clip"].read_text() == "old"

    @pytest.mark.asyncio
    async def test_text_never_stays_on_an_initially_empty_clipboard(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path]
    ) -> None:
        fake_x_tools["clip"].write_text("")

        result = await backend.type_text("你好")

        assert result.success is True
        assert fake_x_tools["seen"].read_text() == "你好"
        assert fake_x_tools["clip"].read_text() == ""

    @pytest.mark.asyncio
    async def test_overlapping_pastes_run_one_after_the_other_and_the_clipboard_comes_back(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDOTOOL_DELAY", "0.4")
        first = asyncio.create_task(backend.type_text("你好"))
        # The second call starts while the first one's text is on the clipboard and its Ctrl+V is in flight.
        for _ in range(500):
            if fake_x_tools["entered"].exists():
                break
            await asyncio.sleep(0.01)
        assert fake_x_tools["entered"].exists()
        second = asyncio.create_task(backend.type_text("世界"))

        results = await asyncio.gather(first, second)

        assert [r.success for r in results] == [True, True]
        assert fake_x_tools["seen"].read_text() == "你好世界"
        assert fake_x_tools["clip"].read_text() == "old"

    @pytest.mark.asyncio
    async def test_unresponsive_clipboard_owner_cannot_stall_the_paste(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stuck_read = f"30.{os.getpid()}"  # unique, so pgrep can only match this test's sleep
        monkeypatch.setenv("XCLIP_HANG", stuck_read)
        monkeypatch.setattr(linux_module, "_CLIPBOARD_READ_TIMEOUT_S", 0.3)

        result = await asyncio.wait_for(backend.type_text("你好"), timeout=10)

        assert result.success is True
        assert fake_x_tools["seen"].read_text() == "你好"
        # The unreadable original cannot be restored; the pasted text must still not stay behind.
        assert fake_x_tools["clip"].read_text() == ""
        assert not [p for p in psutil.process_iter(["cmdline"]) if stuck_read in " ".join(p.info["cmdline"] or [])]


class TestRunCmdTimeout:
    @pytest.mark.asyncio
    async def test_timeout_that_lands_after_the_process_exited_is_still_reported_as_a_timeout(
        self, backend: LinuxBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def expire_after_the_command_finished(awaitable: Awaitable[object], timeout: float | None) -> object:
            await awaitable
            raise TimeoutError

        monkeypatch.setattr(linux_module.asyncio, "wait_for", expire_after_the_command_finished)

        stdout, _, code = await backend._run_cmd("true", timeout=1)

        assert (stdout, code) == ("", 124)


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
    async def test_non_ascii_secret_is_pasted_and_the_clipboard_comes_back(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], vault_secret: Callable[[str], None]
    ) -> None:
        vault_secret("密码-S3cr3t")

        result = await backend.type_credential("bank")

        assert result.success is True
        assert fake_x_tools["seen"].read_text() == "密码-S3cr3t"
        assert fake_x_tools["clip"].read_text() == "old"
        assert "密码" not in fake_x_tools["argv"].read_text()

    @pytest.mark.asyncio
    async def test_secret_never_stays_on_an_initially_empty_clipboard(
        self, backend: LinuxBackend, fake_x_tools: dict[str, Path], vault_secret: Callable[[str], None]
    ) -> None:
        fake_x_tools["clip"].write_text("")
        vault_secret("密码-S3cr3t")

        await backend.type_credential("bank")

        assert fake_x_tools["clip"].read_text() == ""
