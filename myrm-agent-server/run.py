#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""应用启动脚本

所有部署模式默认使用 uvicorn 单进程（沙箱内嵌入式 SQLite + Qdrant 需要单进程避免文件锁冲突）。
如需手动切换为 granian 多进程，设置 SERVER_MODE=granian（仅适用于无嵌入式数据库的场景）。

启动逻辑已拆分到 app/startup/ 子模块，本文件仅作为 CLI 入口。
"""

import argparse
import os

from app.core.infra.frontend_launcher import find_available_port
from app.startup.config_check import run_config_check
from app.startup.env_loader import init_environment
from app.startup.granian_runner import start_with_granian
from app.startup.server_lock import acquire_server_lock
from app.startup.uvicorn_runner import start_with_uvicorn

# 环境初始化（必须最先执行）
init_environment()

# Fail closed when production harness wheels are incomplete (passes in editable dev)
from myrm_agent_harness._distribution import (  # noqa: E402
    DistributionMode,
    assert_distribution_ready,
    get_distribution_mode,
)

assert_distribution_ready()

_mode = get_distribution_mode()
_mode_labels: dict[DistributionMode, str] = {
    DistributionMode.SOURCE: "editable/源码 (本地开发)",
    DistributionMode.COMPILED: "PyPI 编译包 (接近生产)",
    DistributionMode.INCOMPLETE: "不完整 — 请运行 install_harness_dev.sh",
}
print(f"📦 Harness 安装形态: {_mode_labels.get(_mode, _mode.value)}")

# 配置校验与迁移
run_config_check()

# 从环境变量读取默认端口和主机地址
_default_port = int(os.getenv("PORT", "8080"))
_default_host = os.getenv("HOST", "0.0.0.0")


def _should_use_granian() -> bool:
    """是否使用 granian 多进程模式。默认 uvicorn 单进程。"""
    return os.getenv("SERVER_MODE", "").lower() == "granian"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动应用服务器")
    parser.add_argument(
        "--skip-port-check",
        action="store_true",
        help="跳过端口占用检查",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=None,
        help=f"指定端口号（默认从 PORT 环境变量读取，无则为 {_default_port}）",
    )
    parser.add_argument(
        "-H",
        "--host",
        type=str,
        default=None,
        help=f"指定主机地址（默认从 HOST 环境变量读取，无则为 {_default_host}）",
    )
    parser.add_argument(
        "--webui",
        action="store_true",
        help="启动 WebUI 模式（浏览器访问模式）",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="允许远程访问（仅 WebUI 模式有效，绑定到 0.0.0.0）",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="不自动打开浏览器（仅 WebUI 模式有效）",
    )
    parser.add_argument(
        "--no-qrcode",
        action="store_true",
        help="不显示二维码（仅 WebUI 模式有效）",
    )
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="跳过启动前的资源健康检查",
    )
    parser.add_argument(
        "--no-auto-recovery",
        action="store_true",
        help="禁用自动恢复（健康检查失败时不尝试修复）",
    )
    parser.add_argument(
        "--force-recovery",
        action="store_true",
        help="允许危险的恢复操作（例如删除 SQLite WAL 文件，可能导致数据丢失）",
    )
    args = parser.parse_args()

    # 处理 WebUI 模式参数
    if args.webui:
        preferred_port = args.port if args.port is not None else 25808
        if args.remote:
            host = "0.0.0.0"
        else:
            host = args.host or "127.0.0.1"
        os.environ.setdefault("DEPLOY_MODE", "local")
        os.environ["WEBUI_MODE"] = "true"
        os.environ["WEBUI_REMOTE_MODE"] = "true" if args.remote else "false"
    else:
        preferred_port = args.port if args.port is not None else _default_port
        host = args.host if args.host is not None else _default_host
        os.environ.setdefault("DEPLOY_MODE", "local")

    # 获取 OS 级文件锁，避免多开冲突
    if not args.skip_port_check:
        acquire_server_lock(preferred_port)

    # 自动探测可用端口（避免端口冲突）
    if not args.skip_port_check:
        port = find_available_port(preferred_port, host)
        if port != preferred_port:
            print(f"\n⚠️  端口 {preferred_port} 已被占用，已自动切换到 {port}")
            print(f"💡 后端实际端口: http://{host}:{port}\n")
        else:
            port = preferred_port
    else:
        port = preferred_port

    print(f"🔧 配置: host={host}, port={port}")

    if _should_use_granian():
        start_with_granian(
            host=host,
            port=port,
            skip_port_check=args.skip_port_check,
            skip_health_check=args.skip_health_check,
            no_auto_recovery=args.no_auto_recovery,
            force_recovery=args.force_recovery,
        )
    else:
        start_with_uvicorn(
            host=host,
            port=port,
            skip_port_check=args.skip_port_check,
            webui_mode=args.webui,
            remote_mode=args.remote,
            no_browser=args.no_browser,
            no_qrcode=args.no_qrcode,
            skip_health_check=args.skip_health_check,
            no_auto_recovery=args.no_auto_recovery,
            force_recovery=args.force_recovery,
        )
