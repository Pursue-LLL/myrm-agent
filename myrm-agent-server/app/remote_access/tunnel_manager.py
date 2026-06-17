"""Cloudflare quick tunnel lifecycle for G1-global remote access.

[POS]
Manage cloudflared quick tunnel subprocess and watchdog for remote WebUI ingress.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)
_WATCHDOG_INTERVAL_SECONDS = 5.0


class TunnelState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class TunnelStatus:
    state: TunnelState
    public_url: str = ""
    error: str = ""
    provider: str = "cloudflare_quick"


class TunnelManager:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._state = TunnelState.STOPPED
        self._public_url = ""
        self._error = ""
        self._lock = asyncio.Lock()
        self._watchdog_task: asyncio.Task[None] | None = None

    def status(self) -> TunnelStatus:
        return TunnelStatus(
            state=self._state,
            public_url=self._public_url,
            error=self._error,
        )

    async def start(self, *, local_port: int) -> TunnelStatus:
        async with self._lock:
            if self._state == TunnelState.RUNNING and self._public_url:
                return self.status()
            await self._stop_locked()
            if shutil.which("cloudflared") is None:
                self._state = TunnelState.ERROR
                self._error = "cloudflared binary not found in PATH"
                return self.status()

            self._state = TunnelState.STARTING
            self._error = ""
            self._public_url = ""
            try:
                self._process = await asyncio.create_subprocess_exec(
                    "cloudflared",
                    "tunnel",
                    "--url",
                    f"http://127.0.0.1:{local_port}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                self._state = TunnelState.ERROR
                self._error = str(exc)
                return self.status()

            assert self._process.stderr is not None
            deadline = asyncio.get_running_loop().time() + 45.0
            while asyncio.get_running_loop().time() < deadline:
                if self._process.returncode is not None:
                    break
                line_bytes = await asyncio.wait_for(self._process.stderr.readline(), timeout=5.0)
                if not line_bytes:
                    continue
                line = line_bytes.decode("utf-8", errors="ignore")
                match = _URL_PATTERN.search(line)
                if match:
                    self._public_url = match.group(0)
                    self._state = TunnelState.RUNNING
                    logger.info("Cloudflare quick tunnel ready: %s", self._public_url)
                    self._ensure_watchdog()
                    return self.status()

            await self._stop_locked()
            self._state = TunnelState.ERROR
            self._error = "Timed out waiting for cloudflared public URL"
            return self.status()

    async def stop(self) -> TunnelStatus:
        async with self._lock:
            await self._stop_locked()
            return self.status()

    async def shutdown(self) -> None:
        await self.stop()
        await self._cancel_watchdog()

    def _ensure_watchdog(self) -> None:
        if self._watchdog_task is not None and not self._watchdog_task.done():
            return
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def _cancel_watchdog(self) -> None:
        task = self._watchdog_task
        self._watchdog_task = None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _watchdog_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(_WATCHDOG_INTERVAL_SECONDS)
                async with self._lock:
                    process = self._process
                    if process is None:
                        continue
                    if process.returncode is None:
                        continue
                    self._state = TunnelState.ERROR
                    self._error = f"cloudflared exited with code {process.returncode}"
                    self._public_url = ""
                    self._process = None
                    logger.warning("Cloudflare quick tunnel exited: %s", self._error)
        except asyncio.CancelledError:
            raise

    async def _stop_locked(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        self._state = TunnelState.STOPPED
        self._public_url = ""
        self._error = ""


_tunnel_manager = TunnelManager()


def get_tunnel_manager() -> TunnelManager:
    return _tunnel_manager


__all__ = ["TunnelManager", "TunnelState", "TunnelStatus", "get_tunnel_manager"]
