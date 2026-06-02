import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
# Root tests/conftest.py already loads .env + [T] test secrets.


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def cleanup_old_temp_dirs():
    """清理遗留的测试目录，防止磁盘泄漏"""
    tmp_path = Path(tempfile.gettempdir())
    now = time.time()
    for prefix in ["myrm_test_", "myrm_harness_test_", "myrm_e2e_ws_"]:
        for d in tmp_path.glob(f"{prefix}*"):
            if d.is_dir():
                try:
                    mtime = d.stat().st_mtime
                    if now - mtime > 3600:  # 1小时未修改
                        shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass


def pytest_sessionstart(session):
    """全局会话开始前执行垃圾回收"""
    cleanup_old_temp_dirs()


def _probe_frontend(url: str) -> bool:
    client = httpx.Client(timeout=2.0)
    base = url.rstrip("/")
    try:
        for path in ("/health", ""):
            resp = client.get(f"{base}{path}")
            if resp.status_code in (200, 307, 308):
                return True
    except Exception:
        return False
    return False


@pytest.fixture(scope="session")
def ephemeral_server():
    """启动一个独立的后端测试服务器沙箱"""
    port = get_free_port()
    ws_dir = tempfile.mkdtemp(prefix="myrm_e2e_ws_")

    env = os.environ.copy()
    env["MYRM_DATA_DIR"] = ws_dir
    env["DEPLOY_MODE"] = "local"
    env["PORT"] = str(port)
    env["SKIP_HEALTH_CHECK"] = "true"

    server_dir = Path(__file__).parent.parent.parent.parent / "myrm-agent-server"

    # 拉起进程
    log_file = open(ws_dir + "/server.log", "w")
    proc = subprocess.Popen(
        ["uv", "run", "run.py", "--port", str(port)],
        cwd=str(server_dir),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # 等待健康检查通过
    url = f"http://127.0.0.1:{port}"
    max_retries = 30
    ready = False

    client = httpx.Client(timeout=1.0)
    for _ in range(max_retries):
        try:
            resp = client.get(f"{url}/api/v1/health")
            if resp.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)
        if proc.poll() is not None:
            break

    if not ready:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        raise RuntimeError(f"Ephemeral server failed to start on port {port}.")

    yield url

    # 清理
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(ws_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def ephemeral_frontend(ephemeral_server):
    """Prefer an already-running dev server; otherwise start an isolated Next instance."""
    preferred: list[str] = []
    if os.getenv("FRONTEND_URL"):
        preferred.append(os.getenv("FRONTEND_URL", "").rstrip("/"))
    preferred.append("http://127.0.0.1:3000")

    for candidate in preferred:
        if candidate and _probe_frontend(candidate):
            yield candidate
            return

    backend_url = ephemeral_server
    backend_port = backend_url.split(":")[-1]

    frontend_port = get_free_port()

    env = os.environ.copy()
    env["API_PORT"] = str(backend_port)
    env["PORT"] = str(frontend_port)

    frontend_dir = Path(__file__).parent.parent.parent.parent / "myrm-agent-frontend"

    dev_lock = frontend_dir / ".next" / "dev" / "lock"
    if dev_lock.exists():
        dev_lock.unlink(missing_ok=True)

    # scripts/dev.ts pins port 3000; start Next directly on the ephemeral port.
    frontend_log = Path(tempfile.mkdtemp(prefix="myrm_e2e_fe_")) / "frontend.log"
    log_file = open(frontend_log, "w")
    proc = subprocess.Popen(
        ["bunx", "next", "dev", "-p", str(frontend_port)],
        cwd=str(frontend_dir),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    url = f"http://127.0.0.1:{frontend_port}"
    max_retries = 90
    ready = False

    client = httpx.Client(timeout=2.0)
    for _ in range(max_retries):
        try:
            for probe in (f"{url}/health", url):
                resp = client.get(probe)
                if resp.status_code in (200, 307, 308):
                    ready = True
                    break
            if ready:
                break
        except Exception:
            pass
        time.sleep(1)
        if proc.poll() is not None:
            break

    if not ready:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        log_tail = ""
        try:
            log_tail = frontend_log.read_text(encoding="utf-8")[-4000:]
        except Exception:
            pass
        raise RuntimeError(f"Ephemeral frontend failed to start on port {frontend_port}. Log tail:\n{log_tail}")

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
