"""[INPUT]
- .common / .checks / .assets / .ports (POS: launcher collaborators)

[OUTPUT]
- FrontendLauncher, launch_frontend, _LogPrefixPipe

[POS]
Frontend launcher: process lifecycle, log piping and the public entrypoint.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import threading
import time
from typing import TextIO

from . import assets, checks, ports
from .common import (
    _HEALTH_CHECK_TIMEOUT,
    _MAX_RESTART_ATTEMPTS,
    _TOXIC_NODE_ENV_VARS,
    FrontendEnvironmentError,
    _resolve_standalone_dir,
    logger,
)


class _LogPrefixPipe(threading.Thread):
    """Forward subprocess output line-by-line with a prefix."""

    daemon = True

    def __init__(self, source: TextIO, prefix: str, target_level: int = logging.INFO) -> None:
        super().__init__()
        self._source = source
        self._prefix = prefix
        self._level = target_level

    def run(self) -> None:
        try:
            for line in self._source:
                stripped = line.rstrip("\n\r")
                if stripped:
                    logger.log(self._level, "%s %s", self._prefix, stripped)
        except ValueError:
            pass


class FrontendLauncher:
    """Manages the Next.js standalone server lifecycle.

    Primary cleanup: FastAPI lifespan shutdown calls stop().
    Fallback cleanup: atexit handler (for non-uvicorn exits).
    """

    def __init__(
        self,
        *,
        frontend_port: int = 3000,
        api_port: int = 25808,
        api_host: str = "127.0.0.1",
        bind_host: str = "127.0.0.1",
    ) -> None:
        self._frontend_port = frontend_port
        self._api_port = api_port
        self._api_host = api_host
        self._bind_host = bind_host
        self._process: subprocess.Popen[str] | None = None
        self._restart_count = 0
        self._shutdown_event = threading.Event()
        self._log_threads: list[_LogPrefixPipe] = []
        self._atexit_registered = False

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._frontend_port}"

    def start(self) -> bool:
        """Start the Next.js standalone server.

        Returns:
            True if the server started and passed health check.
        """
        checks.check_build_artifacts()
        assets.ensure_standalone_assets()
        assets.patch_nextjs_rewrites(self._api_host, self._api_port)

        actual_port = ports.find_available_port(self._frontend_port, self._bind_host)
        if actual_port != self._frontend_port:
            print(f"\n⚠️  前端端口 {self._frontend_port} 已被占用，已自动切换到 {actual_port}")
            print(f"💡 前端实际端口: http://{self._bind_host}:{actual_port}\n")
            logger.info(
                "[Frontend] Port %d in use, using %d instead",
                self._frontend_port,
                actual_port,
            )
            self._frontend_port = actual_port

        from myrm_agent_harness.api import (
            EnvInheritPolicy,
            build_isolated_child_env,
        )

        extra_frontend_env = {
            "PORT": str(self._frontend_port),
            "HOSTNAME": self._bind_host,
            "NODE_ENV": "production",
            "API_HOST": self._api_host,
            "API_PORT": str(self._api_port),
        }
        env = build_isolated_child_env(
            base_env=None,
            extra_env=extra_frontend_env,
            inherit_policy=EnvInheritPolicy.CORE,
        )
        for var in _TOXIC_NODE_ENV_VARS:
            env.pop(var, None)

        # 架构升级：基于 stdin 管道的自杀机制，彻底解决僵尸进程问题
        # Python 退出（即使是被 SIGKILL 异常杀死），OS 都会自动关闭管道。
        # Node 端监听到 stdin 上的 end/close 事件即可实现确定性自动退出。
        wrapper_code = """
        process.stdin.resume();
        process.on('SIGINT', () => { console.log('[Frontend-Wrapper] SIGINT received'); process.exit(0); });
        process.on('SIGTERM', () => { console.log('[Frontend-Wrapper] SIGTERM received'); process.exit(0); });
        
        // Only exit on stdin close/end if we haven't been running for very long, or if we are actually shutting down
        // It seems stdin might be closing prematurely or intermittently
        process.stdin.on('end', () => { console.log('[Frontend-Wrapper] stdin end'); process.exit(0); });
        process.stdin.on('close', () => { console.log('[Frontend-Wrapper] stdin close'); process.exit(0); });
        process.stdin.on('error', (err) => { console.error('[Frontend-Wrapper] stdin error:', err); process.exit(0); });
        
        process.on('uncaughtException', (err) => {
            console.error('[Frontend-Wrapper] Uncaught Exception:', err);
            // Don't exit immediately on uncaught exception to see if it's a transient Next.js error
            // process.exit(1);
        });
        process.on('unhandledRejection', (reason, promise) => {
            console.error('[Frontend-Wrapper] Unhandled Rejection at:', promise, 'reason:', reason);
            // Don't exit immediately on unhandled rejection
            // process.exit(1);
        });

        console.log('[Frontend-Wrapper] Starting server.js...');
        require('./server.js');
        """

        standalone_dir = _resolve_standalone_dir()
        self._process = subprocess.Popen(
            ["node", "-e", wrapper_code],
            cwd=str(standalone_dir),
            env=env,
            stdin=subprocess.PIPE,  # 核心：建立管道
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if not self._atexit_registered:
            atexit.register(self.stop)
            self._atexit_registered = True

        stdout_pipe = _LogPrefixPipe(self._process.stdout, "[Frontend]")  # type: ignore[arg-type]
        stderr_pipe = _LogPrefixPipe(self._process.stderr, "[Frontend]", logging.WARNING)  # type: ignore[arg-type]
        stdout_pipe.start()
        stderr_pipe.start()
        self._log_threads = [stdout_pipe, stderr_pipe]

        logger.info(
            "[Frontend] Starting Next.js on port %d (PID %d)",
            self._frontend_port,
            self._process.pid,
        )

        if ports._wait_for_health(self.url):
            logger.info("[Frontend] Ready at %s", self.url)
            return True

        logger.error("[Frontend] Health check timed out after %ds", _HEALTH_CHECK_TIMEOUT)
        return False

    def stop(self) -> None:
        """Gracefully stop the Next.js server."""
        self._shutdown_event.set()
        proc = self._process
        if proc is None or proc.poll() is not None:
            return

        pid = proc.pid
        logger.info("[Frontend] Stopping Next.js (PID %d)...", pid)
        try:
            if proc.stdin:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            try:
                proc.terminate()
            except Exception:
                pass
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            logger.warning("[Frontend] Graceful stop timed out, force killing PID %d", pid)
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        except ProcessLookupError:
            pass
        self._process = None

    def monitor(self) -> None:
        """Monitor the subprocess and restart on crash (up to MAX_RESTART_ATTEMPTS).

        Should be called from a daemon thread.
        """
        while not self._shutdown_event.is_set():
            proc = self._process
            if proc is None:
                break

            proc.wait()
            exit_code = proc.returncode

            if self._shutdown_event.is_set():
                break

            # If exit_code is 0, it means the frontend exited cleanly (e.g. via SIGTERM from watchdog)
            # We shouldn't treat this as a crash that needs restarting if we're shutting down,
            # but if we're not shutting down, it's still unexpected.
            if exit_code == 0:
                logger.warning("[Frontend] Exited unexpectedly with code 0 while not shutting down. Restarting...")
                # We should restart it if we are not shutting down
                pass

            if self._restart_count >= _MAX_RESTART_ATTEMPTS:
                logger.error(
                    "[Frontend] Crashed %d times (exit code %d), giving up",
                    self._restart_count,
                    exit_code,
                )
                break

            self._restart_count += 1
            logger.warning(
                "[Frontend] Crashed (exit code %d), restarting (%d/%d)...",
                exit_code,
                self._restart_count,
                _MAX_RESTART_ATTEMPTS,
            )
            time.sleep(1)
            self.start()

    def _ppid_watchdog(self, original_ppid: int) -> None:
        """Detect parent process death when launched via wrapper (e.g. `uv run`).

        When the wrapper dies without forwarding SIGTERM, Python gets reparented
        (ppid changes). This watchdog detects that, stops the frontend, and sends
        SIGTERM to the current process to trigger uvicorn's graceful shutdown.
        """
        while not self._shutdown_event.is_set():
            if os.getppid() != original_ppid:
                logger.info(
                    "[Frontend] Parent process %d exited, triggering shutdown",
                    original_ppid,
                )
                self.stop()
                os.kill(os.getpid(), signal.SIGTERM)
                return
            self._shutdown_event.wait(timeout=1)


def launch_frontend(
    *,
    api_port: int,
    api_host: str = "127.0.0.1",
    frontend_port: int = 3000,
    bind_host: str = "127.0.0.1",
) -> FrontendLauncher | None:
    """High-level entry point: check environment, start frontend, return launcher.

    Returns:
        FrontendLauncher instance if successful, None on failure.
    """
    try:
        node_version = checks.check_node_environment()
        logger.info("[Frontend] Node.js %s detected", node_version)
    except FrontendEnvironmentError as exc:
        print(f"⚠️  {exc}")
        return None

    try:
        checks.check_build_artifacts()
    except FrontendEnvironmentError as exc:
        print(f"⚠️  {exc}")
        return None

    launcher = FrontendLauncher(
        frontend_port=frontend_port,
        api_port=api_port,
        api_host=api_host,
        bind_host=bind_host,
    )

    if not launcher.start():
        launcher.stop()
        print("⚠️  Frontend failed to start. WebUI will run in API-only mode.")
        return None

    monitor_thread = threading.Thread(target=launcher.monitor, daemon=True)
    monitor_thread.start()

    ppid = os.getppid()
    if ppid != 1:
        watchdog = threading.Thread(target=launcher._ppid_watchdog, args=(ppid,), daemon=True)
        watchdog.start()

    return launcher
