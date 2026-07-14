import os
import shutil
import socket
import subprocess
import sys
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

    log_path = Path(ws_dir) / "server.log"
    log_file = log_path.open("w")
    proc = subprocess.Popen(
        [sys.executable, "run.py", "--port", str(port)],
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

    try:
        if not ready:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
            raise RuntimeError(f"Ephemeral server failed to start on port {port}.")

        yield url
    finally:
        log_file.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(ws_dir, ignore_errors=True)
