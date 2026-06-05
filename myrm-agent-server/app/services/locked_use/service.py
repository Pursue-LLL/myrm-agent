"""LockedUseService — orchestrates screen unlock for Computer Use sessions.

Provides an async context manager that:
1. Acquires a display-aware sleep inhibitor (IOKit / ES_DISPLAY_REQUIRED)
2. Detects if the screen is locked
3. If locked and Locked Use is enabled, temporarily unlocks the screen
4. Re-locks the screen and releases the inhibitor on exit

[INPUT]
- app.services.infra.sleep_inhibitor.SleepInhibitor (display keep-awake)
- macOS Keychain (for password retrieval)

[OUTPUT]
- LockedUseSession: async context manager for CU sessions

[POS]
Business-layer coordinator for Computer Use screen access.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class MacScreenUnlocker:
    """macOS-specific screen lock detection and unlock logic."""

    KEYCHAIN_SERVICE = "com.myrm.agent.screen-unlock"
    KEYCHAIN_ACCOUNT = "login-password"

    @classmethod
    def is_locked(cls) -> bool:
        script = """
            use framework "Foundation"
            set sessionDict to current application's CGSessionCopyCurrentDictionary() as record
            try
                set isLocked to |CGSSessionScreenIsLocked| of sessionDict
                if isLocked is 1 then return "locked"
            end try
            return "unlocked"
        """
        try:
            result = subprocess.run(["osascript", "-l", "AppleScript", "-e", script], capture_output=True, text=True, check=True)
            return result.stdout.strip().lower() == "locked"
        except Exception:
            return False

    @classmethod
    def get_password(cls) -> str | None:
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", cls.KEYCHAIN_SERVICE, "-a", cls.KEYCHAIN_ACCOUNT, "-w"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except Exception:
            return None

    @classmethod
    async def unlock(cls) -> bool:
        password = cls.get_password()
        if not password:
            logger.warning("Screen is locked but no password found in Keychain")
            return False

        # Wake display
        subprocess.Popen(["caffeinate", "-u", "-t", "2"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(0.5)

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
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
            await asyncio.sleep(1.0)
            if cls.is_locked():
                logger.error("Screen still locked after unlock attempt (wrong password?)")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to unlock screen: {e}")
            return False

    @classmethod
    def relock(cls) -> None:
        script = 'tell application "System Events" to keystroke "q" using {control down, command down}'
        subprocess.run(["osascript", "-e", script], capture_output=True)


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
    Layer 2 (Screen Unlock) only activates when config.enabled is True and
    the screen is actually locked.

    Example::

        async with locked_use_session(LockedUseConfig(enabled=True)):
            result = await computer_session.take_screenshot()
    """
    from app.services.infra.sleep_inhibitor import SleepInhibitor

    cfg = config or LockedUseConfig()
    is_mac = platform.system() == "Darwin"
    was_unlocked_by_us = False

    async with SleepInhibitor.hold(prevent_display_sleep=True):
        logger.debug("Display keep-awake acquired for CU session")

        if cfg.enabled and is_mac:
            if MacScreenUnlocker.is_locked():
                logger.info("Screen is locked. Attempting temporary unlock for CU session...")
                was_unlocked_by_us = await MacScreenUnlocker.unlock()
                if was_unlocked_by_us:
                    logger.info("Screen successfully unlocked")

        try:
            yield
        finally:
            if was_unlocked_by_us:
                logger.info("CU session ended. Re-locking screen...")
                MacScreenUnlocker.relock()

        logger.debug("CU session ended, releasing display keep-awake")
