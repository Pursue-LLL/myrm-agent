"""Zero-config Chromium installation for the browser launcher.

[INPUT]
- asyncio (POS: install subprocess, install lock and deadlines)
- patchright CLI, run as ``python -m patchright install chromium`` (POS: Chromium download)
- urllib.request (POS: CDN reachability probe)

[OUTPUT]
- auto_install_chromium: installs Chromium, one install at a time; a failed install blocks the next attempt for 30 minutes
- build_install_failure_message: user-facing text for a failed automatic install, with the manual command and a mirror hint

[POS]
Called by ``BrowserLauncher`` when a launch reports a missing Chromium executable (the first run of a desktop install).
The download uses the default Playwright CDN, or the npmmirror mirror when the CDN does not answer within 5 s.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

_INSTALL_TIMEOUT_S = 600  # 10 minutes max for Chromium download
_INSTALL_COOLDOWN_S = 1800  # 30 minutes cooldown after failed install

_install_lock: asyncio.Lock | None = None
_last_install_failure_at: float = 0.0

_CDN_PROBE_URL = "https://cdn.playwright.dev"
_CN_MIRROR_HOST = "https://cdn.npmmirror.com/binaries/playwright"
_CN_MIRROR_CHROMIUM_HOST = "https://cdn.npmmirror.com/binaries/chrome-for-testing"
_CDN_PROBE_TIMEOUT_S_INSTALL = 5.0


def _get_install_env() -> dict[str, str]:
    """Build env dict for patchright install with CDN mirror fallback.

    Respects user-set PLAYWRIGHT_DOWNLOAD_HOST. When unset, probes the
    default Playwright CDN; if unreachable within 5 s (common in mainland
    China / corporate firewalls), falls back to npmmirror.
    """
    env = dict(os.environ)
    if env.get("PLAYWRIGHT_DOWNLOAD_HOST"):
        return env

    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(_CDN_PROBE_URL, method="HEAD")
        urllib.request.urlopen(req, timeout=_CDN_PROBE_TIMEOUT_S_INSTALL)  # noqa: S310
    except urllib.error.HTTPError:
        pass  # HTTP 4xx/5xx means server is reachable
    except Exception:
        env["PLAYWRIGHT_DOWNLOAD_HOST"] = _CN_MIRROR_HOST
        env["PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST"] = _CN_MIRROR_CHROMIUM_HOST
        logger.info("Default Playwright CDN unreachable — using npmmirror (%s)", _CN_MIRROR_HOST)
    return env


async def auto_install_chromium() -> bool:
    """Install Chromium via patchright with cooldown protection.

    Returns True if installation succeeded, False otherwise.
    Prevents repeated attempts within _INSTALL_COOLDOWN_S after a failure.
    """
    global _last_install_failure_at, _install_lock

    if _last_install_failure_at and (time.monotonic() - _last_install_failure_at) < _INSTALL_COOLDOWN_S:
        remaining = int(_INSTALL_COOLDOWN_S - (time.monotonic() - _last_install_failure_at))
        logger.warning("Chromium auto-install skipped: previous failure cooldown (%ds remaining)", remaining)
        return False

    if _install_lock is None:
        _install_lock = asyncio.Lock()

    async with _install_lock:
        # Double-check after acquiring lock
        if _last_install_failure_at and (time.monotonic() - _last_install_failure_at) < _INSTALL_COOLDOWN_S:
            return False

        logger.info("Auto-installing Chromium via patchright (this may take a few minutes)...")
        try:
            env = await asyncio.get_running_loop().run_in_executor(None, _get_install_env)
            # Invoke via `python -m patchright` so install works regardless of PATH
            # (the `patchright` CLI may live in a venv bin dir that is not on PATH).
            install_args = [sys.executable, "-m", "patchright", "install", "chromium"]
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *install_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                ),
                timeout=_INSTALL_TIMEOUT_S,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_INSTALL_TIMEOUT_S)

            if proc.returncode == 0:
                logger.info("Chromium auto-install succeeded")
                _last_install_failure_at = 0.0
                return True

            _last_install_failure_at = time.monotonic()
            logger.error(
                "Chromium auto-install failed (exit %d): %s",
                proc.returncode,
                (stderr or stdout or b"").decode(errors="replace")[:500],
            )
            return False

        except TimeoutError:
            _last_install_failure_at = time.monotonic()
            logger.error("Chromium auto-install timed out after %ds", _INSTALL_TIMEOUT_S)
            return False
        except FileNotFoundError:
            _last_install_failure_at = time.monotonic()
            logger.error("'patchright' CLI not found — cannot auto-install Chromium")
            return False
        except Exception as exc:
            _last_install_failure_at = time.monotonic()
            logger.error("Chromium auto-install unexpected error: %s", exc)
            return False


def build_install_failure_message(original_error: Exception) -> str:
    """Build a user-friendly error message when auto-install fails.

    Includes diagnostic hints (disk space, network, permissions) to help
    GUI users who cannot easily run terminal commands.
    """
    lines = [
        "Browser engine (Chromium) is not installed and automatic installation failed.",
        "",
        "To fix this manually, open a terminal and run:",
        "  patchright install chromium",
        "",
        "If the download is slow or fails (e.g. in mainland China), use a mirror:",
        f"  PLAYWRIGHT_DOWNLOAD_HOST={_CN_MIRROR_HOST} patchright install chromium",
        "",
        "Common causes:",
        "  - Insufficient disk space (Chromium requires ~400 MB)",
        "  - No internet connection (download required)",
        "  - Permission issues (try running with elevated privileges)",
        "",
        f"Original error: {original_error}",
    ]
    return "\n".join(lines)
