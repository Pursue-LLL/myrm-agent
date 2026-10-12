"""[INPUT]
- os, signal, logging
- psutil::{Process, net_connections, NoSuchProcess, AccessDenied}
- fastapi::{APIRouter, HTTPException, Path, status}
- pydantic::{BaseModel, Field}

[OUTPUT]
- router: APIRouter for port inspection, process lineage tracking, and safe process termination
- inspect_port, get_process_lineage, kill_process
- PortInspectResponse, ProcessLineageNode, ProcessKillRequest, ProcessKillResponse

[POS]
app/api/system/port_inspector.py — 系统端口占用一键排查、父子进程树溯源与安全查杀端点。
"""

from __future__ import annotations

import logging
import os
import signal
import time
from typing import Annotated

import psutil
from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system-port-inspector"])

# 系统关键守护进程保护集合
PROTECTED_PIDS: frozenset[int] = frozenset({0, 1})
PROTECTED_PROCESS_NAMES: frozenset[str] = frozenset({
    "launchd",
    "systemd",
    "init",
    "kernel_task",
    "kthreadd",
    "loginwindow",
    "syslogd",
})


class PortProcessInfo(BaseModel):
    """端口占用进程明细模型。"""

    pid: int = Field(..., description="进程唯一 PID")
    name: str = Field(..., description="进程可执行名称")
    cmdline: list[str] = Field(default_factory=list, description="完整启动命令行参数")
    cpu_percent: float = Field(0.0, description="CPU 占用率百分比")
    memory_mb: float = Field(0.0, description="物理内存驻留集大小 (MB)")
    status: str = Field("running", description="进程运行状态")
    username: str = Field("", description="启动该进程的用户名称")
    cwd: str | None = Field(None, description="进程当前工作目录")
    create_time: float = Field(0.0, description="进程创建时间戳")
    is_protected: bool = Field(False, description="是否属于系统受保护进程")


class ProcessLineageNode(BaseModel):
    """父子进程树节点模型。"""

    pid: int = Field(..., description="进程 PID")
    ppid: int = Field(..., description="父进程 PID")
    name: str = Field(..., description="进程名称")
    cmdline: list[str] = Field(default_factory=list, description="启动命令行参数")
    cwd: str | None = Field(None, description="当前工作目录")
    username: str = Field("", description="启动用户名")
    is_high_resource: bool = Field(False, description="是否为高资源消耗进程 (CPU>50% 或 内存>500MB)")


class PortInspectResponse(BaseModel):
    """端口检测综合分析响应。"""

    port: int = Field(..., description="检测的目标端口")
    is_in_use: bool = Field(..., description="端口是否已被占用")
    process: PortProcessInfo | None = Field(None, description="占用该端口的进程信息")
    lineage: list[ProcessLineageNode] = Field(default_factory=list, description="进程从根到当前的父子派生链")


class ProcessKillRequest(BaseModel):
    """终止进程请求模型。"""

    force: bool = Field(False, description="是否强制查杀 (SIGKILL 替代 SIGTERM)")
    reason: str = Field("port_conflict_resolution", description="查杀原因说明")


class ProcessKillResponse(BaseModel):
    """终止进程操作结果模型。"""

    success: bool = Field(..., description="操作是否成功")
    pid: int = Field(..., description="被操作的进程 PID")
    signal_sent: str = Field(..., description="发送的操作信号名称 (SIGTERM/SIGKILL)")
    message: str = Field(..., description="操作执行说明")


def _is_process_protected(proc: psutil.Process) -> bool:
    """判定进程是否受系统保护或属于当前服务自身。"""
    if proc.pid in PROTECTED_PIDS or proc.pid == os.getpid():
        return True
    try:
        if proc.name().lower() in PROTECTED_PROCESS_NAMES:
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return False


def get_process_lineage(pid: int) -> list[ProcessLineageNode]:
    """向上回溯指定 PID 的父进程派生链路，直至 PID 1 或根节点。"""
    lineage_nodes: list[ProcessLineageNode] = []
    curr_pid = pid

    visited: set[int] = set()
    while curr_pid > 0 and curr_pid not in visited:
        visited.add(curr_pid)
        try:
            p = psutil.Process(curr_pid)
            ppid = p.ppid()
            try:
                cmd = p.cmdline()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                cmd = []
            try:
                cwd = p.cwd()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                cwd = None
            try:
                uname = p.username()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                uname = ""
            try:
                cpu = p.cpu_percent(interval=None)
                mem = p.memory_info().rss / (1024 * 1024)
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                cpu, mem = 0.0, 0.0

            lineage_nodes.append(
                ProcessLineageNode(
                    pid=p.pid,
                    ppid=ppid,
                    name=p.name(),
                    cmdline=cmd,
                    cwd=cwd,
                    username=uname,
                    is_high_resource=(cpu > 50.0 or mem > 500.0),
                )
            )
            curr_pid = ppid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break

    # 反转列表，使其从根祖先 (launchd/systemd) 流向当前目标进程
    lineage_nodes.reverse()
    return lineage_nodes


def find_process_on_port(port: int) -> psutil.Process | None:
    """跨平台探测在指定端口监听连接的进程。"""
    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        connections = []

    for conn in connections:
        if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN and conn.pid:
            try:
                return psutil.Process(conn.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    # 若 net_connections 未授权或未能检索，降级遍历所有运行中进程
    for p in psutil.process_iter(["pid"]):
        try:
            for c in p.net_connections(kind="inet"):
                if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN:
                    return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return None


@router.get(
    "/ports/{port}/inspect",
    response_model=PortInspectResponse,
    summary="探测指定端口是否冲突被占，并提取占用进程明细与启动链路",
)
async def inspect_port_endpoint(
    port: Annotated[int, Path(ge=1, le=65535, description="目标端口号")],
) -> PortInspectResponse:
    """全方位排查端口占用状态，溯源启动父子进程树，协助用户快速决策是否释放。"""
    proc = find_process_on_port(port)
    if proc is None:
        return PortInspectResponse(port=port, is_in_use=False, process=None, lineage=[])

    try:
        try:
            cmd = proc.cmdline()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            cmd = []
        try:
            cwd = proc.cwd()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            cwd = None
        try:
            uname = proc.username()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            uname = ""
        try:
            cpu = proc.cpu_percent(interval=None)
            mem = proc.memory_info().rss / (1024 * 1024)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            cpu, mem = 0.0, 0.0

        proc_info = PortProcessInfo(
            pid=proc.pid,
            name=proc.name(),
            cmdline=cmd,
            cpu_percent=round(cpu, 1),
            memory_mb=round(mem, 1),
            status=proc.status(),
            username=uname,
            cwd=cwd,
            create_time=proc.create_time(),
            is_protected=_is_process_protected(proc),
        )
        lineage = get_process_lineage(proc.pid)
        return PortInspectResponse(
            port=port,
            is_in_use=True,
            process=proc_info,
            lineage=lineage,
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return PortInspectResponse(port=port, is_in_use=False, process=None, lineage=[])


@router.get(
    "/processes/{pid}/lineage",
    response_model=list[ProcessLineageNode],
    summary="逆向回溯指定进程的父子派生调用链",
)
async def process_lineage_endpoint(
    pid: Annotated[int, Path(ge=1, description="目标进程 PID")],
) -> list[ProcessLineageNode]:
    """回溯进程完整的派生链，例如 launchd -> zsh -> node -> worker，查明谁拉起了高耗任务。"""
    try:
        psutil.Process(pid)
    except psutil.NoSuchProcess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process with PID {pid} not found.",
        )
    return get_process_lineage(pid)


@router.post(
    "/processes/{pid}/kill",
    response_model=ProcessKillResponse,
    summary="安全终止指定进程以释放冲突端口或终止僵尸进程",
)
async def kill_process_endpoint(
    pid: Annotated[int, Path(ge=1, description="待查杀进程 PID")],
    payload: ProcessKillRequest | None = None,
) -> ProcessKillResponse:
    """终止进程。内置受保护进程防火墙，禁止误杀系统守护进程及服务自身。"""
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Process with PID {pid} does not exist.",
        )

    # 严格安全白名单过滤
    if _is_process_protected(proc):
        logger.warning("Rejected attempt to kill protected process %s (%s)", pid, proc.name())
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Process {pid} ({proc.name()}) is a critical protected system process and cannot be killed.",
        )

    force = payload.force if payload else False
    sig_name = "SIGKILL" if force else "SIGTERM"
    sig = signal.SIGKILL if force else signal.SIGTERM

    try:
        proc.send_signal(sig)
        time.sleep(0.05)  # 短暂缓冲允许进程退出收敛
        logger.info("Successfully sent %s to process %s (reason: %s)", sig_name, pid, payload.reason if payload else "")
        return ProcessKillResponse(
            success=True,
            pid=pid,
            signal_sent=sig_name,
            message=f"已成功向进程 {pid} 发送 {sig_name} 终止信号。",
        )
    except psutil.AccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied to send signal to PID {pid}.",
        )
    except psutil.NoSuchProcess:
        return ProcessKillResponse(
            success=True,
            pid=pid,
            signal_sent=sig_name,
            message=f"进程 {pid} 已在信号发送前退出。",
        )
