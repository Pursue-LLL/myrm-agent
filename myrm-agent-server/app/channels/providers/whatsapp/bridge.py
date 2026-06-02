"""WhatsApp Baileys bridge subprocess management.

Handles spawning, stdin/stdout IPC, and lifecycle of the Node.js bridge
process. Designed as a mixin so WhatsAppChannel can inherit bridge
operations without bloating the main channel module.

[INPUT]
- helpers::_BRIDGE_DIR, _BRIDGE_SCRIPT, _PROCESS_STOP_TIMEOUT (POS: path constants)

[OUTPUT]
- BridgeProcessMixin: subprocess spawn, IPC read/write, graceful shutdown

[POS]
Bridge process management. WhatsAppChannel inherits spawn/read/write/kill via Mixin;
channel.py focuses on business logic (event dispatch, messaging).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.channels.providers.whatsapp.helpers import (
    _BRIDGE_DIR,
    _BRIDGE_SCRIPT,
    _PROCESS_STOP_TIMEOUT,
)
from app.channels.types import ChannelStatus

logger = logging.getLogger(__name__)

_BRIDGE_SCRIPT_NAME = "whatsapp-bridge"


def _is_bridge_process(pid: int) -> bool:
    """Check if *pid* is alive and its command line contains the bridge script name."""
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False

    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return _BRIDGE_SCRIPT_NAME in result.stdout
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return _BRIDGE_SCRIPT_NAME in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


class BridgeProcessMixin:
    """Mixin providing Node.js Baileys bridge subprocess management.

    Expects the host class to have:
    - ``_process``: ``asyncio.subprocess.Process | None``
    - ``_reader_task``: ``asyncio.Task[None] | None``
    - ``_auth_dir``: ``Path``
    - ``_connected``: ``asyncio.Event``
    - ``_status``: ``ChannelStatus``
    - ``_status``: property setter auto-broadcasts status_change events
    - ``_handle_bridge_event(raw: str)``: event dispatcher (async)
    """

    _process: asyncio.subprocess.Process | None
    _reader_task: asyncio.Task[None] | None
    _connected: asyncio.Event

    async def _ensure_node_deps(self) -> None:
        """Install npm dependencies if node_modules is missing."""
        node_modules = _BRIDGE_DIR / "node_modules"
        if node_modules.exists():
            return

        node_bin = shutil.which("node")
        npm_bin = shutil.which("npm")
        if not node_bin:
            raise RuntimeError("Node.js not found — required for WhatsApp bridge")
        if not npm_bin:
            raise RuntimeError("npm not found — required for WhatsApp bridge")

        logger.warning("WhatsAppChannel: installing bridge dependencies...")
        proc = await asyncio.create_subprocess_exec(
            npm_bin,
            "install",
            "--production",
            cwd=str(_BRIDGE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"npm install failed (exit {proc.returncode}): {stderr.decode()[:500]}")
        logger.warning("WhatsAppChannel: bridge dependencies installed")

    @property
    def _pid_file(self) -> Path:
        return self._auth_dir / "bridge.pid"  # type: ignore[attr-defined]

    def _kill_stale_bridge(self) -> None:
        """Kill any orphaned bridge process from a previous run."""
        pid_file = self._pid_file
        if not pid_file.exists():
            return

        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            pid_file.unlink(missing_ok=True)
            return

        if not _is_bridge_process(pid):
            pid_file.unlink(missing_ok=True)
            return

        logger.warning("WhatsAppChannel: killing stale bridge process (pid=%d)", pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pid_file.unlink(missing_ok=True)
            return

        for _ in range(4):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        pid_file.unlink(missing_ok=True)

    def _write_pid_file(self) -> None:
        if self._process and self._process.pid:
            try:
                self._pid_file.write_text(str(self._process.pid))
            except OSError:
                pass

    def _remove_pid_file(self) -> None:
        self._pid_file.unlink(missing_ok=True)

    async def _spawn_bridge(self) -> None:
        """Spawn the Node.js bridge subprocess.

        Kills any orphaned bridge from a previous run before spawning.
        """
        self._kill_stale_bridge()

        node_bin = shutil.which("node")
        if not node_bin:
            raise RuntimeError("Node.js not found")

        self._auth_dir.mkdir(parents=True, exist_ok=True)  # type: ignore[attr-defined]

        env = os.environ.copy()
        for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]:
            env.pop(key, None)

        self._process = await asyncio.create_subprocess_exec(
            node_bin,
            str(_BRIDGE_SCRIPT),
            str(self._auth_dir),  # type: ignore[attr-defined]
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._write_pid_file()
        self._reader_task = asyncio.create_task(self._read_stdout())
        asyncio.create_task(self._read_stderr())

    async def _read_stderr(self) -> None:
        """Read stderr from bridge process for error logging."""
        if not self._process or not self._process.stderr:
            return

        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                decoded = line.decode().strip()
                if decoded:
                    if "error" in decoded.lower() or "exception" in decoded.lower():
                        logger.error("WhatsAppChannel: bridge stderr: %s", decoded)
                    else:
                        logger.info("WhatsAppChannel: bridge stderr: %s", decoded)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error("WhatsAppChannel: stderr reader error: %s", exc)

    async def _read_stdout(self) -> None:
        """Read JSON Lines from bridge stdout and dispatch events."""
        if not self._process or not self._process.stdout:
            return

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                await self._handle_bridge_event(line.decode().strip())  # type: ignore[attr-defined]
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("WhatsAppChannel: stdout reader error: %s", exc)
        finally:
            if self._status == ChannelStatus.RUNNING:  # type: ignore[attr-defined]
                self._status = ChannelStatus.ERROR  # type: ignore[attr-defined]
                self._connected.clear()
                logger.warning("WhatsAppChannel: bridge process ended unexpectedly")

    def _write_cmd(self, cmd: dict[str, object]) -> None:
        """Write a JSON Line command to the bridge stdin."""
        if self._process and self._process.stdin:
            data = json.dumps(cmd) + "\n"
            self._process.stdin.write(data.encode())

    async def _drain(self) -> None:
        """Flush the stdin write buffer to the bridge subprocess."""
        if self._process and self._process.stdin:
            try:
                await self._process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass

    async def _kill_process(self) -> None:
        """Terminate the bridge subprocess gracefully and clean up PID file."""
        if not self._process:
            return

        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=_PROCESS_STOP_TIMEOUT)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()

        self._process = None
        self._remove_pid_file()
