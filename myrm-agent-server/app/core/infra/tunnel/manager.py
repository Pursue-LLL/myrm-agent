"""Cloudflare Quick Tunnel process lifecycle (local deployments only).

[INPUT]
- app.config.deploy_mode::is_sandbox (POS: 部署模式判定)
- app.core.infra.ingress::set_runtime_tunnel_ingress (POS: 公网 Ingress 解析)
- app.services.config.service::config_service (POS: UserConfig 持久化)

[OUTPUT]
- TunnelManager: start/stop/status for Quick Tunnel
- get_tunnel_manager: process-wide singleton
- parse_quick_tunnel_url_from_line: extract trycloudflare URL from one log line
- parse_quick_tunnel_url_from_output: extract URL from multi-line cloudflared output

[POS]
本地/WebUI 部署的 Quick Tunnel 唯一进程宿主。SANDBOX 与 CP 注入 ingress 场景禁用。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from dataclasses import dataclass

from app.config.deploy_mode import is_sandbox
from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.infra import ingress as ingress_module
from app.services.config.service import config_service

logger = logging.getLogger(__name__)

_TUNNEL_URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
_READINESS_TIMEOUT_SECONDS = 90.0
_STDERR_LOG_TAIL_LINES = 30
_DEVICE_ID = "tunnel-manager"


def parse_quick_tunnel_url_from_line(line: str) -> str | None:
    """Return the first Quick Tunnel URL found in a single cloudflared log line."""
    match = _TUNNEL_URL_RE.search(line)
    return match.group(0) if match else None


def parse_quick_tunnel_url_from_output(output: str) -> str | None:
    """Return the first Quick Tunnel URL found in multi-line cloudflared stderr/stdout."""
    for line in output.splitlines():
        found = parse_quick_tunnel_url_from_line(line)
        if found:
            return found
    return None


class TunnelError(Exception):
    """Raised when tunnel operations fail."""


@dataclass(frozen=True)
class TunnelStatus:
    running: bool
    url: str | None
    target_port: int | None
    ingress_synced: bool


class TunnelManager:
    """Single-process Cloudflare Quick Tunnel host."""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._url: str | None = None
        self._target_port: int | None = None
        self._ingress_snapshot: str | None = None
        self._lock = asyncio.Lock()

    def _resolve_cloudflared_binary(self) -> str:
        configured = os.getenv("CLOUDFLARED_PATH", "").strip()
        if configured and os.path.isfile(configured) and os.access(configured, os.X_OK):
            return configured
        found = shutil.which("cloudflared")
        if found:
            return found
        raise TunnelError("cloudflared binary not found. Install cloudflared or set CLOUDFLARED_PATH.")

    @staticmethod
    def _ensure_quick_tunnel_allowed() -> None:
        if is_sandbox():
            raise TunnelError("Quick Tunnel is not available in sandbox mode. Use platform ingress.")
        from app.config.settings import settings

        if settings.cp_public_ingress_url.strip():
            raise TunnelError("Quick Tunnel is disabled when CP_PUBLIC_INGRESS_URL is set. Use platform ingress.")

    async def _load_personal_settings(self) -> dict[str, object]:
        record = await config_service.get("personalSettings")
        if record is None or not isinstance(record.value, dict):
            return {}
        return dict(record.value)

    async def _persist_public_ingress(self, url: str | None) -> None:
        if not url and self._ingress_snapshot is None:
            return

        personal = await self._load_personal_settings()
        updated = dict(personal)
        if url:
            updated["publicIngressBaseUrl"] = url
        elif self._ingress_snapshot:
            updated["publicIngressBaseUrl"] = self._ingress_snapshot
        else:
            updated.pop("publicIngressBaseUrl", None)

        await config_service.set("personalSettings", updated, device_id=_DEVICE_ID)
        invalidate_user_configs_cache()

    async def _sync_ingress_runtime(self, url: str | None) -> None:
        ingress_module.set_runtime_tunnel_ingress(url)
        await self._persist_public_ingress(url)

    async def start(self, port: int, *, password_protection_enabled: bool) -> TunnelStatus:
        if port < 1 or port > 65535:
            raise TunnelError("Invalid tunnel target port.")

        if not password_protection_enabled:
            raise TunnelError("Password protection must be enabled before starting a public tunnel.")

        self._ensure_quick_tunnel_allowed()

        async with self._lock:
            if self._process is not None and self._process.returncode is None:
                return TunnelStatus(
                    running=True,
                    url=self._url,
                    target_port=self._target_port,
                    ingress_synced=bool(self._url),
                )

            await self._reset_tunnel_state_unlocked()

            binary = self._resolve_cloudflared_binary()
            personal = await self._load_personal_settings()
            self._ingress_snapshot = str(personal.get("publicIngressBaseUrl", "") or "").strip() or None

            self._process = await asyncio.create_subprocess_exec(
                binary,
                "tunnel",
                "--url",
                f"http://127.0.0.1:{port}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._target_port = port
            self._url = None

            try:
                self._url = await self._await_tunnel_url(self._process)
            except Exception as exc:
                await self._terminate_process()
                if isinstance(exc, TunnelError):
                    raise
                raise TunnelError(str(exc)) from exc

            await self._sync_ingress_runtime(self._url)
            logger.info("Quick Tunnel started: %s -> localhost:%s", self._url, port)

            return TunnelStatus(
                running=True,
                url=self._url,
                target_port=self._target_port,
                ingress_synced=True,
            )

    @staticmethod
    def _log_cloudflared_failure(
        process: asyncio.subprocess.Process,
        stderr_lines: list[str],
        *,
        reason: str,
    ) -> None:
        tail = "\n".join(stderr_lines[-_STDERR_LOG_TAIL_LINES:])
        logger.error(
            "Quick Tunnel failed (%s); cloudflared exit=%s; stderr tail:\n%s",
            reason,
            process.returncode,
            tail or "(no stderr captured)",
        )

    async def _await_tunnel_url(self, process: asyncio.subprocess.Process) -> str:
        if process.stderr is None:
            raise TunnelError("cloudflared stderr pipe is unavailable.")

        stderr_lines: list[str] = []

        async def _read_stream(
            stream: asyncio.StreamReader,
            *,
            capture_stderr: bool = False,
        ) -> str | None:
            while True:
                line = await stream.readline()
                if not line:
                    return None
                text = line.decode("utf-8", errors="replace")
                if capture_stderr:
                    stderr_lines.append(text.rstrip())
                found = parse_quick_tunnel_url_from_line(text)
                if found:
                    return found
            return None

        async def _wait_for_url() -> str:
            assert process.stderr is not None
            stderr_task = asyncio.create_task(
                _read_stream(process.stderr, capture_stderr=True),
            )
            stdout_task = None
            if process.stdout is not None:
                stdout_task = asyncio.create_task(_read_stream(process.stdout))

            pending: set[asyncio.Task[str | None]] = {stderr_task}
            if stdout_task is not None:
                pending.add(stdout_task)

            try:
                while pending:
                    done, pending = await asyncio.wait(
                        pending,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        found = task.result()
                        if found:
                            for other in pending:
                                other.cancel()
                            return found
                    if process.returncode is not None:
                        break
            finally:
                for task in pending:
                    task.cancel()

            exit_code = process.returncode
            if exit_code is not None and exit_code != 0:
                self._log_cloudflared_failure(
                    process,
                    stderr_lines,
                    reason=f"exited with code {exit_code}",
                )
                raise TunnelError(f"cloudflared exited with code {exit_code} before publishing a URL.")
            self._log_cloudflared_failure(process, stderr_lines, reason="no URL in output")
            raise TunnelError("Failed to parse tunnel URL from cloudflared output.")

        try:
            return await asyncio.wait_for(_wait_for_url(), timeout=_READINESS_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            self._log_cloudflared_failure(process, stderr_lines, reason="timed out waiting for URL")
            raise TunnelError("Timed out waiting for tunnel URL from cloudflared.") from exc

    async def _terminate_process(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except TimeoutError:
                process.kill()
                await process.wait()

    async def _reset_tunnel_state_unlocked(self) -> None:
        """Reset tunnel process and ingress snapshot. Caller must hold ``_lock``."""
        await self._terminate_process()
        self._url = None
        self._target_port = None
        await self._sync_ingress_runtime(None)
        self._ingress_snapshot = None

    async def stop(self) -> TunnelStatus:
        async with self._lock:
            await self._reset_tunnel_state_unlocked()
            logger.info("Quick Tunnel stopped")
            return TunnelStatus(
                running=False,
                url=None,
                target_port=None,
                ingress_synced=False,
            )

    async def _cleanup_dead_process(self) -> None:
        exit_code = self._process.returncode if self._process else None
        logger.warning("Quick Tunnel process exited (code=%s), clearing state", exit_code)
        self._process = None
        self._url = None
        self._target_port = None
        await self._sync_ingress_runtime(None)
        self._ingress_snapshot = None

    async def get_status(self) -> TunnelStatus:
        async with self._lock:
            if self._process is not None and self._process.returncode is not None:
                await self._cleanup_dead_process()
            running = self._process is not None and self._process.returncode is None
            return TunnelStatus(
                running=running,
                url=self._url if running else None,
                target_port=self._target_port if running else None,
                ingress_synced=bool(self._url) and running,
            )


_manager: TunnelManager | None = None


def get_tunnel_manager() -> TunnelManager:
    global _manager
    if _manager is None:
        _manager = TunnelManager()
    return _manager
