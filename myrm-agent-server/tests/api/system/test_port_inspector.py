"""[INPUT]
- httpx, ASGITransport
- socket, os, subprocess, time
- app.api.system.port_inspector::router

[OUTPUT]
- Pytest test cases verifying port inspection, lineage tracing, security barriers, and safe termination.

[POS]
tests/api/system/test_port_inspector.py — 系统端口冲突排查、进程树溯源与查杀 API 单元测试。
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.system.port_inspector import router as port_inspector_router

test_app = FastAPI()
test_app.include_router(port_inspector_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_inspect_unused_port(async_client: httpx.AsyncClient) -> None:
    # 找一个临时空闲端口并立即释放
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]

    resp = await async_client.get(f"/api/v1/system/ports/{free_port}/inspect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["port"] == free_port
    assert data["is_in_use"] is False
    assert data["process"] is None
    assert len(data["lineage"]) == 0


@pytest.mark.asyncio
async def test_inspect_active_listening_port(async_client: httpx.AsyncClient) -> None:
    # 绑定并监听一个临时端口
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    bound_port = server_sock.getsockname()[1]

    try:
        resp = await async_client.get(f"/api/v1/system/ports/{bound_port}/inspect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["port"] == bound_port
        assert data["is_in_use"] is True
        assert data["process"] is not None
        assert data["process"]["pid"] == os.getpid()
        assert data["process"]["is_protected"] is True  # 当前服务自身受保护
        assert len(data["lineage"]) >= 1
    finally:
        server_sock.close()


@pytest.mark.asyncio
async def test_process_lineage_endpoint(async_client: httpx.AsyncClient) -> None:
    current_pid = os.getpid()
    resp = await async_client.get(f"/api/v1/system/processes/{current_pid}/lineage")
    assert resp.status_code == 200
    nodes = resp.json()
    assert isinstance(nodes, list)
    assert len(nodes) >= 1
    # 最后一项应该为当前目标进程
    assert nodes[-1]["pid"] == current_pid

    # 针对不存在的 PID 返回 404
    not_found_resp = await async_client.get("/api/v1/system/processes/99999999/lineage")
    assert not_found_resp.status_code == 404


@pytest.mark.asyncio
async def test_security_barrier_protects_system_pid_1(async_client: httpx.AsyncClient) -> None:
    # 尝试查杀 PID 1 必须被安全防火墙 403 拦截
    resp = await async_client.post("/api/v1/system/processes/1/kill", json={"force": True})
    assert resp.status_code == 403
    assert "critical protected system process" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_kill_non_existent_process_returns_404(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.post("/api/v1/system/processes/99999999/kill")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_safe_kill_user_child_process(async_client: httpx.AsyncClient) -> None:
    # 启动一个短暂存活的子进程作为测试靶标
    proc = subprocess.Popen(["sleep", "30"])
    target_pid = proc.pid

    try:
        resp = await async_client.post(
            f"/api/v1/system/processes/{target_pid}/kill",
            json={"force": True, "reason": "pytest_verification"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["pid"] == target_pid
        assert data["signal_sent"] == "SIGKILL"

        # 验证进程已退出
        time.sleep(0.1)
        ret = proc.poll()
        assert ret is not None
    finally:
        if proc.poll() is None:
            proc.kill()
