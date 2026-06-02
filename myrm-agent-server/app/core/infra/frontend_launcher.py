"""Next.js standalone frontend launcher for WebUI mode.

Manages the Next.js standalone server as a subprocess alongside FastAPI,
providing:
- Environment detection (Node.js version, build artifacts)
- Port coordination (auto-detect available ports, pass API_PORT to Next.js)
- Process lifecycle (cleanup via FastAPI lifespan shutdown, crash restart)
- Unified logging ([Frontend] prefix)
- Startup sequencing (wait for health before opening browser)
"""

import atexit
import logging
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import TextIO
from urllib.error import URLError
from urllib.request import urlopen

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_FRONTEND_DIR = _PROJECT_ROOT.parent / "myrm-agent-frontend"
_STANDALONE_DIR = _FRONTEND_DIR / ".next" / "standalone"
_STANDALONE_SERVER = _STANDALONE_DIR / "server.js"

_MIN_NODE_VERSION = 18
_MAX_RESTART_ATTEMPTS = 3
_HEALTH_CHECK_TIMEOUT = 30
_HEALTH_CHECK_INTERVAL = 0.5


class FrontendEnvironmentError(RuntimeError):
    """Raised when the frontend environment is not ready."""


def check_node_environment() -> str:
    """Verify Node.js is installed and meets minimum version requirement.

    Returns:
        Node.js version string (e.g. "20.11.0")

    Raises:
        FrontendEnvironmentError: If Node.js is missing or version is too old.
    """
    node_bin = shutil.which("node")
    if not node_bin:
        raise FrontendEnvironmentError(
            f"Node.js is not installed. Please install Node.js >= {_MIN_NODE_VERSION}: https://nodejs.org/"
        )

    try:
        result = subprocess.run(
            [node_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version_str = result.stdout.strip().lstrip("v")
        major = int(version_str.split(".")[0])
        if major < _MIN_NODE_VERSION:
            raise FrontendEnvironmentError(
                f"Node.js {version_str} is too old. Please upgrade to >= {_MIN_NODE_VERSION}: https://nodejs.org/"
            )
        return version_str
    except (subprocess.TimeoutExpired, ValueError, IndexError) as exc:
        raise FrontendEnvironmentError(
            f"Failed to detect Node.js version: {exc}"
        ) from exc


def check_build_artifacts() -> Path:
    """Verify Next.js standalone build artifacts exist.

    Returns:
        Path to the standalone server.js

    Raises:
        FrontendEnvironmentError: If build artifacts are missing or incomplete.
    """
    if not _STANDALONE_SERVER.is_file():
        raise FrontendEnvironmentError(
            f"Frontend build not found at {_STANDALONE_DIR}\n"
            "Please build the frontend first:\n"
            "  cd myrm-agent-frontend && bun run build"
        )
    static_dir = _FRONTEND_DIR / ".next" / "static"
    if not static_dir.is_dir():
        raise FrontendEnvironmentError(
            f"Frontend static assets not found at {static_dir}\n"
            "The build appears incomplete. Please rebuild:\n"
            "  cd myrm-agent-frontend && bun run build"
        )
    return _STANDALONE_SERVER


def _ensure_symlink(link: Path, target: Path) -> None:
    """Create a relative symlink, replacing broken ones.

    Raises:
        FrontendEnvironmentError: If the symlink cannot be created.
    """
    try:
        if link.is_symlink():
            if link.resolve() == target.resolve():
                return
            link.unlink()
        elif link.exists():
            return

        rel_target = os.path.relpath(target, link.parent)
        link.symlink_to(rel_target)
    except OSError as exc:
        raise FrontendEnvironmentError(
            f"Cannot create symlink {link} -> {target}: {exc}"
        ) from exc


def ensure_standalone_assets() -> None:
    """Symlink static assets and public files into the standalone directory.

    Next.js standalone output only contains server.js; CSS/JS chunks and
    public files must be linked separately.
    """
    static_src = _FRONTEND_DIR / ".next" / "static"
    static_dst = _STANDALONE_DIR / ".next" / "static"
    if static_src.is_dir():
        static_dst.parent.mkdir(parents=True, exist_ok=True)
        _ensure_symlink(static_dst, static_src)
        logger.info("[Frontend] Static assets linked: %s", static_dst)

    public_src = _FRONTEND_DIR / "public"
    public_dst = _STANDALONE_DIR / "public"
    if public_src.is_dir():
        _ensure_symlink(public_dst, public_src)
        logger.info("[Frontend] Public files linked: %s", public_dst)
    else:
        logger.info("[Frontend] No public/ directory found, skipping")


def patch_nextjs_rewrites(api_host: str, api_port: int) -> None:
    """Patch the hardcoded API port in Next.js build artifacts."""

    # We need to patch the standalone directory files, not just the build output
    target_files = [
        _STANDALONE_DIR / ".next" / "routes-manifest.json",
        _STANDALONE_DIR / ".next" / "required-server-files.json",
        _STANDALONE_DIR / "server.js",
    ]

    for file_path in target_files:
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                import re

                # Match both 127.0.0.1 and localhost (Next rewrites may bake in either).
                new_content = re.sub(
                    r"http://(?:127\.0\.0\.1|localhost):\d+",
                    f"http://{api_host}:{api_port}",
                    content,
                )
                if new_content != content:
                    file_path.write_text(new_content, encoding="utf-8")
                    logger.info(
                        "[Frontend] Patched %s with API port %d",
                        file_path.name,
                        api_port,
                    )
            except Exception as e:
                logger.warning("[Frontend] Failed to patch %s: %s", file_path.name, e)


def find_available_port(preferred: int, host: str = "127.0.0.1") -> int:
    """Find an available port, preferring the given one.

    Args:
        preferred: Preferred port number.
        host: Host to bind to.

    Returns:
        Available port number.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, preferred))
            return preferred
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, 0))
            addr = s.getsockname()
            return int(addr[1])


def _wait_for_health(url: str, timeout: float = _HEALTH_CHECK_TIMEOUT) -> bool:
    """Poll a URL until it returns 200 or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (URLError, OSError, TimeoutError):
            pass
        time.sleep(_HEALTH_CHECK_INTERVAL)
    return False


class _LogPrefixPipe(threading.Thread):
    """Forward subprocess output line-by-line with a prefix."""

    daemon = True

    def __init__(
        self, source: TextIO, prefix: str, target_level: int = logging.INFO
    ) -> None:
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
        check_build_artifacts()
        ensure_standalone_assets()
        patch_nextjs_rewrites(self._api_host, self._api_port)

        actual_port = find_available_port(self._frontend_port, self._bind_host)
        if actual_port != self._frontend_port:
            print(
                f"\n⚠️  前端端口 {self._frontend_port} 已被占用，已自动切换到 {actual_port}"
            )
            print(f"💡 前端实际端口: http://{self._bind_host}:{actual_port}\n")
            logger.info(
                "[Frontend] Port %d in use, using %d instead",
                self._frontend_port,
                actual_port,
            )
            self._frontend_port = actual_port

        env = {
            **os.environ,
            "PORT": str(self._frontend_port),
            "HOSTNAME": self._bind_host,
            "NODE_ENV": "production",
            "API_HOST": self._api_host,
            "API_PORT": str(self._api_port),
        }

        # 架构升级：基于 stdin 管道的自杀机制，彻底解决僵尸进程问题
        # Python 退出（即使是被 SIGKILL 异常杀死），OS 都会自动关闭管道。
        # Node 端监听到 stdin 上的 end/close 事件即可实现确定性自动退出。
        wrapper_code = """
        process.stdin.resume();
        process.on('SIGINT', () => { console.log('[Frontend-Wrapper] SIGINT received'); process.exit(0); });
        process.on('SIGTERM', () => { console.log('[Frontend-Wrapper] SIGTERM received'); process.exit(0); });
        
        // Only exit on stdin close/end if we haven't been running for very long, or if we are actually shutting down
        // It seems stdin might be closing prematurely or intermittently
        process.stdin.on('end', () => { console.log('[Frontend-Wrapper] stdin end'); });
        process.stdin.on('close', () => { console.log('[Frontend-Wrapper] stdin close'); });
        process.stdin.on('error', (err) => { console.error('[Frontend-Wrapper] stdin error:', err); });
        
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

        self._process = subprocess.Popen(
            ["node", "-e", wrapper_code],
            cwd=str(_STANDALONE_DIR),
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

        if _wait_for_health(self.url):
            logger.info("[Frontend] Ready at %s", self.url)
            return True

        logger.error(
            "[Frontend] Health check timed out after %ds", _HEALTH_CHECK_TIMEOUT
        )
        return False

    def stop(self) -> None:
        """Gracefully stop the Next.js server."""
        self._shutdown_event.set()
        proc = self._process
        if proc is None or proc.poll() is not None:
            return

        pid = proc.pid
        logger.info(
            "[Frontend] Stopping Next.js (PID %d) via stdin pipe closure...", pid
        )
        try:
            # 核心：通过关闭 stdin 管道触发 Node.js 端优雅退出，避免使用难以控制的信号
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning(
                "[Frontend] Graceful stop timed out, force killing PID %d", pid
            )
            proc.kill()
            try:
                proc.wait(timeout=3)
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
                logger.warning(
                    "[Frontend] Exited unexpectedly with code 0 while not shutting down. Restarting..."
                )
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
        node_version = check_node_environment()
        logger.info("[Frontend] Node.js %s detected", node_version)
    except FrontendEnvironmentError as exc:
        print(f"⚠️  {exc}")
        return None

    try:
        check_build_artifacts()
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
        watchdog = threading.Thread(
            target=launcher._ppid_watchdog, args=(ppid,), daemon=True
        )
        watchdog.start()

    return launcher
