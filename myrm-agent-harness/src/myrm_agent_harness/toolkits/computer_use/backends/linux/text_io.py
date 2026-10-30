"""Linux X11 text entry — reliable typing for ASCII and any other script.

[INPUT]
- (none: commands run through callables the backend hands in, so display and cancellation handling stay in one place)

[OUTPUT]
- X11TextInput: enter(text) types pure-ASCII text as key events and pastes any text with a non-ASCII character through the clipboard
- RunCmd, RunInput: the command-runner shapes X11TextInput relies on

[POS]
Text bridge of the Linux backend. xdotool synthesizes a non-ASCII character by remapping a spare keycode
per character, and the application can read that key event before the remap lands, so a character drops or
turns into another one; the clipboard path delivers the whole text in one keystroke and restores the
user's clipboard afterwards. ASCII keeps the key-event path because it needs neither xclip nor a clipboard.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from typing import Protocol

logger = logging.getLogger(__name__)

# A stuck clipboard owner makes `xclip -o` block forever; healthy owners answer in milliseconds.
_CLIPBOARD_READ_TIMEOUT_S = 3.0
# The target application reads the clipboard when it handles Ctrl+V; restoring earlier would hand it the old content.
_PASTE_SETTLE_S = 0.1


class RunCmd(Protocol):
    """Run a command and return (stdout, stderr, exit code); `timeout` kills it and reports exit 124."""

    def __call__(
        self, cmd: str, stdin: str | None = None, timeout: float | None = None, *, capture: bool = True
    ) -> Awaitable[tuple[str, str, int]]: ...


class RunInput(Protocol):
    """Run a command and raise RuntimeError when it exits non-zero."""

    def __call__(self, cmd: str, stdin: str | None = None, *, capture: bool = True) -> Awaitable[None]: ...


class X11TextInput:
    """Enters text into the focused X11 window."""

    def __init__(self, run: RunCmd, run_input: RunInput) -> None:
        self._run = run
        self._run_input = run_input
        # Pastes borrow the clipboard; overlapping ones would save each other's temporary text as the user's original.
        self._clipboard_lock = asyncio.Lock()

    async def enter(self, text: str, delay_ms: int = 12, chunk_size: int = 50) -> None:
        """Enter `text`; raises RuntimeError when the input tool fails."""
        if text.isascii():
            await self._type_ascii(text, delay_ms, chunk_size)
        else:
            await self._paste(text)

    async def _type_ascii(self, text: str, delay_ms: int, chunk_size: int) -> None:
        """Type in chunks so a long text is not one uninterruptible call; the text goes over stdin, out of the process list."""
        for start in range(0, len(text), chunk_size):
            try:
                await self._run_input(
                    f"xdotool type --delay {delay_ms} --file -", stdin=text[start : start + chunk_size]
                )
            except RuntimeError as exc:
                raise RuntimeError(f"{exc}; typed {start} of {len(text)} characters") from exc

    async def _xclip_write(self, text: str) -> None:
        """Replace the clipboard. xclip forks a selection owner that inherits stdout/stderr, so they are not captured."""
        await self._run_input("xclip -selection clipboard", stdin=text, capture=False)

    async def _paste(self, text: str) -> None:
        """Paste through the clipboard and put the user's original clipboard back."""
        async with self._clipboard_lock:
            original, _, _ = await self._run("xclip -selection clipboard -o", timeout=_CLIPBOARD_READ_TIMEOUT_S)
            try:
                await self._xclip_write(text)
                await self._run_input("xdotool key ctrl+v")
                await asyncio.sleep(_PASTE_SETTLE_S)
            finally:
                # An empty or non-text clipboard reads as "": it is still written back, otherwise the pasted text
                # (a credential, say) would stay on the clipboard.
                try:
                    await self._xclip_write(original)
                except Exception:
                    logger.warning("Failed to restore the X11 clipboard after paste", exc_info=True)
