import json
import os
import selectors
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
# Root tests/conftest.py already loads .env + [T] test secrets.

_AGENT_ROOT = _SERVER_ROOT.parent
_PREPARE = _AGENT_ROOT / "scripts/dev/subagent-dashboard-e2e-prepare.mjs"
_PREPARE_PREFIX = "E2E_PREPARE_JSON="

from tests.support.e2e_runtime_guard import E2EResourceLedger  # noqa: E402


def _read_prepare_result(
    process: subprocess.Popen[str], timeout_sec: float
) -> dict[str, object]:
    if process.stdout is None:
        raise RuntimeError("Subagent prepare stdout is unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout_sec
    diagnostics: list[str] = []
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                remainder = process.stdout.read()
                if remainder:
                    diagnostics.extend(remainder.splitlines())
                raise RuntimeError(
                    f"Subagent prepare exited {process.returncode}: {diagnostics[-20:]}"
                )
            events = selector.select(timeout=min(1.0, deadline - time.monotonic()))
            if not events:
                continue
            line = process.stdout.readline().strip()
            if not line:
                continue
            if line.startswith(_PREPARE_PREFIX):
                payload = json.loads(line.removeprefix(_PREPARE_PREFIX))
                if not isinstance(payload, dict):
                    raise RuntimeError(f"Invalid subagent prepare payload: {payload!r}")
                return payload
            diagnostics.append(line)
    finally:
        selector.close()
    raise TimeoutError(f"Subagent prepare timed out: {diagnostics[-20:]}")


@pytest.fixture
def running_subagent(
    e2e_resource_ledger: E2EResourceLedger,
) -> Iterator[dict[str, object]]:
    if shutil.which("bun") is None:
        pytest.skip("bun is required for subagent dashboard prepare")
    if (
        not os.environ.get("BASIC_API_KEY", "").strip()
        or not os.environ.get("BASIC_MODEL", "").strip()
    ):
        pytest.skip("BASIC_API_KEY and BASIC_MODEL are required")
    env = os.environ.copy()
    env["E2E_HOLD_MS"] = "240000"
    env["WAVE_LEDGER_LEASE_ID"] = e2e_resource_ledger.lease_id
    env["WAVE_LEDGER_NAMESPACE"] = e2e_resource_ledger.namespace
    process = subprocess.Popen(
        ["bun", str(_PREPARE)],
        cwd=str(_AGENT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        yield _read_prepare_result(process, timeout_sec=210.0)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


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
