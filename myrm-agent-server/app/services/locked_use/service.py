"""LockedUseService — orchestrates screen unlock for Computer Use sessions.

Provides an async context manager that:
1. Acquires a display-aware sleep inhibitor (IOKit / ES_DISPLAY_REQUIRED)
2. Detects if the screen is locked
3. If locked, Locked Use is enabled and nobody is at the machine, takes the unlock lease and unlocks the screen
4. Re-locks the screen, hands the lease back and releases the inhibitor on exit

[INPUT]
- app.services.infra.sleep_inhibitor.SleepInhibitor (display keep-awake)
- myrm_agent_harness.api.security::get_default_screen_detector / hid_idle_seconds (POS: native screen-lock probe and hardware input idle reading)
- app.services.locked_use.curtain_bridge (lease bit shared with the desktop shell)
- macOS Keychain (for password retrieval)

[OUTPUT]
- MacScreenUnlocker: lock probe / presence probe / serialized unlock / verified re-lock primitives
- release_unlock_lease: re-lock if needed, then hand the lease bit back
- locked_use_session: async context manager for CU sessions

[POS]
Business-layer coordinator for Computer Use screen access.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import re
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from myrm_agent_harness.api.security import ScreenLockState, get_default_screen_detector, hid_idle_seconds

from app.services.locked_use.curtain_bridge import clear_pending_auto_unlock, mark_pending_auto_unlock

logger = logging.getLogger(__name__)

# Serializes password typing: the CU session path and the unattended lease watcher
# can both decide to unlock within the same second, and a second typing run would
# land the password in whatever window has focus on the already-unlocked desktop.
_unlock_guard = asyncio.Lock()

# Ctrl+Cmd+Q — the system lock chord. AppleScript source is a module constant so
# the password-bearing unlock script stays the only dynamically built script.
_RELOCK_SCRIPT = 'tell application "System Events" to keystroke "q" using {control down, command down}'

# How long to wait for the lock chord to take effect before verifying.
_RELOCK_VERIFY_DELAY_SECONDS = 0.8
_RELOCK_ATTEMPTS = 3

# Display wake lead time before typing, and settle time before the unlock is verified.
_UNLOCK_WAKE_DELAY_SECONDS = 0.5
_UNLOCK_SETTLE_DELAY_SECONDS = 1.0

# Someone who touched the keyboard or mouse within this window is at the machine: typing the
# password now would collide with their input and open the screen for whoever stands there.
# It spans several watcher ticks and ordinary pauses at the login window, while an owner who
# walked away delays the unattended run by no more than this.
PRESENCE_IDLE_THRESHOLD_SECONDS = 15.0

# `security find-generic-password -g` reports the secret on stderr as `password: "text"`
# for plain printable data and as `password: 0x<HEX>  "<escaped>"` once it holds anything
# else (non-ASCII, tabs, backslashes). `-w` hex-encodes such data without saying so, which
# cannot be told apart from a password that merely looks like hex.
_KEYCHAIN_PASSWORD_LINE = re.compile(r'^password: (?:0x(?P<hex>[0-9A-Fa-f]+)|"(?P<text>.*)")', re.MULTILINE)


def _parse_keychain_password(security_stderr: str) -> str | None:
    """Decode the password line of ``security find-generic-password -g`` output."""
    match = _KEYCHAIN_PASSWORD_LINE.search(security_stderr)
    if match is None:
        return None
    hex_digits = match.group("hex")
    if hex_digits is None:
        return match.group("text")
    try:
        return bytes.fromhex(hex_digits).decode("utf-8")
    except ValueError:  # odd-length hex, or bytes that are not UTF-8
        return None


class MacScreenUnlocker:
    """macOS-specific screen lock detection and unlock logic."""

    KEYCHAIN_SERVICE = "com.myrm.agent.screen-unlock"
    KEYCHAIN_ACCOUNT = "login-password"

    @classmethod
    def is_locked(cls) -> bool:
        """True only for a definitely locked session (native in-process probe).

        UNKNOWN (probe failure) and SLEEPING (display off, session not locked)
        both count as "not locked", so callers leave the screen alone instead of
        typing a password blindly.
        """
        return get_default_screen_detector().get_state(force_refresh=True) is ScreenLockState.LOCKED

    @classmethod
    def user_present(cls) -> bool:
        """True unless hardware input has been idle long enough to prove nobody is at the machine.

        An unreadable probe counts as present: like :meth:`is_locked`, uncertainty leaves
        the screen alone instead of typing the password blindly.
        """
        idle = hid_idle_seconds()
        return idle is None or idle < PRESENCE_IDLE_THRESHOLD_SECONDS

    @classmethod
    def get_password(cls) -> str | None:
        """Read the unlock password from the Keychain; None when absent, empty or unreadable.

        The output is never logged: it carries the password.
        """
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", cls.KEYCHAIN_SERVICE, "-a", cls.KEYCHAIN_ACCOUNT, "-g"],
                capture_output=True,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return _parse_keychain_password(result.stderr.decode("utf-8", errors="replace")) or None

    @classmethod
    async def unlock(cls) -> bool:
        """Unlock the screen; True when the screen is unlocked afterwards.

        Callers are serialized and the lock state is re-probed under the guard:
        whoever waited finds the screen already unlocked and types nothing. Presence
        is re-probed there too: the caller's own check is stale by the time the
        guard is held, and a person who reached for the machine is never typed over.
        """
        async with _unlock_guard:
            if not cls.is_locked():
                return True
            if cls.user_present():
                logger.info("Unlock deferred: a user is at the machine")
                return False
            return await cls._type_password()

    @classmethod
    async def _type_password(cls) -> bool:
        """Type the Keychain password into the login window.

        The password never leaves this process through argv or logs: the
        AppleScript is fed over stdin (``osascript -``) and failures report
        only the exit code, because ``CalledProcessError.cmd`` / osascript
        stderr can both echo the script body. Blocking subprocess calls run
        off the event loop so the API stays responsive during the ~2 s typing.
        """
        password = await asyncio.to_thread(cls.get_password)
        if not password:
            logger.warning("Screen is locked but no password found in Keychain")
            return False

        # Wake display
        subprocess.Popen(["caffeinate", "-u", "-t", "2"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(_UNLOCK_WAKE_DELAY_SECONDS)

        escaped_password = password.replace("\\", "\\\\").replace('"', '\\"')
        script = f"""
            tell application "System Events"
                key code 49 -- space to wake
                delay 0.5
                keystroke "{escaped_password}"
                delay 0.2
                key code 36 -- return
            end tell
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["osascript", "-"],
                input=script,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            logger.error("Failed to unlock screen: osascript could not be launched")
            return False

        if result.returncode != 0:
            logger.error("Failed to unlock screen: osascript exited with code %d", result.returncode)
            return False

        await asyncio.sleep(_UNLOCK_SETTLE_DELAY_SECONDS)
        if cls.is_locked():
            logger.error("Screen still locked after unlock attempt (wrong password?)")
            return False
        return True

    @classmethod
    def relock(cls) -> bool:
        """Re-lock the screen; True only when the lock primitive reported success.

        The lock primitive is fire-and-forget on some platforms, so callers
        that need certainty must verify with :meth:`is_locked` afterwards.
        """
        result = subprocess.run(
            ["osascript", "-e", _RELOCK_SCRIPT],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            logger.warning("Re-lock command exited with code %d", result.returncode)
            return False
        return True

    @classmethod
    async def relock_verified(cls) -> bool:
        """Re-lock, then confirm with the native probe; bounded retry.

        The lock chord is only a request — a denied keystroke injection exits
        zero without locking anything. Callers must not treat "command ran" as
        "screen is locked", so success is gated on ``is_locked()``.
        """
        for attempt in range(1, _RELOCK_ATTEMPTS + 1):
            await asyncio.to_thread(cls.relock)
            await asyncio.sleep(_RELOCK_VERIFY_DELAY_SECONDS)
            if cls.is_locked():
                return True
            logger.warning("Screen not locked after re-lock attempt %d/%d", attempt, _RELOCK_ATTEMPTS)
        return False

    @classmethod
    async def ensure_locked(cls) -> bool:
        """True when the screen is verifiably locked; the lock chord is sent only when needed."""
        return cls.is_locked() or await cls.relock_verified()


async def release_unlock_lease() -> bool:
    """Re-lock the screen if needed, then hand the lease bit back to the desktop shell.

    The bit is only cleared once the screen is verifiably locked; a screen that
    cannot be locked keeps it set so the curtain stays up (fail-safe).
    """
    if not await MacScreenUnlocker.ensure_locked():
        return False
    clear_pending_auto_unlock()
    return True


@dataclass(frozen=True)
class LockedUseConfig:
    """Configuration for a Locked Use session."""

    enabled: bool = False


@asynccontextmanager
async def locked_use_session(
    config: LockedUseConfig | None = None,
) -> AsyncIterator[None]:
    """Context manager for Computer Use sessions that need screen access.

    Layer 1 (Display Keep-Awake) is always active for CU sessions.
    Layer 2 (Screen Unlock) only activates when config.enabled is True, the
    screen is actually locked and nobody is at the machine.

    Example::

        async with locked_use_session(LockedUseConfig(enabled=True)):
            result = await computer_session.take_screenshot()
    """
    from app.services.infra.sleep_inhibitor import SleepInhibitor

    cfg = config or LockedUseConfig()
    is_mac = platform.system() == "Darwin"
    lease_taken = False

    async with SleepInhibitor.hold(prevent_display_sleep=True):
        logger.debug("Display keep-awake acquired for CU session")

        # The unlock sits inside the try: a failed or cancelled unlock must still
        # hand the lease bit back, otherwise the desktop shell keeps the curtain up.
        try:
            if cfg.enabled and is_mac and MacScreenUnlocker.is_locked():
                if MacScreenUnlocker.user_present():
                    # No lease either: a lease bit left behind would keep the curtain over the
                    # desktop of an owner who then unlocks the screen themselves.
                    logger.info("Screen is locked but a user is at the machine; leaving the unlock to them")
                else:
                    logger.info("Screen is locked. Attempting temporary unlock for CU session...")
                    # Record the lease first: the desktop shell keeps the curtain up while the
                    # screen is unlocked (harmless when there is no curtain / no desktop shell).
                    mark_pending_auto_unlock()
                    lease_taken = True
                    if await MacScreenUnlocker.unlock():
                        logger.info("Screen successfully unlocked")
            yield
        finally:
            if lease_taken:
                logger.info("CU session ended. Releasing the unlock lease...")
                if not await release_unlock_lease():
                    logger.error("Screen could not be re-locked; keeping the curtain lease so the display stays covered")

        logger.debug("CU session ended, releasing display keep-awake")
