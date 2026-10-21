#!/usr/bin/env python3
"""MyrmAgent 部署脚本

支持三种部署模式:
    - tauri:  桌面客户端模式（本地嵌入式数据库，单用户）
    - sandbox: 沙箱模式（控制平面管理的隔离实例）
    - docker: Docker 全栈部署（后端 + 前端 + 数据库，一键启动）

使用方式:
    uv run deploy.py tauri dev          # 桌面端开发模式
    uv run deploy.py tauri build        # 桌面端打包
    uv run deploy.py sandbox             # 沙箱模式
    uv run deploy.py docker             # Docker 全栈部署
    uv run deploy.py status             # 查看服务状态
    uv run deploy.py stop               # 停止所有服务
"""

import argparse
import sys

from deploy_pkg.actions import show_status, start_application, stop_services
from deploy_pkg.docker_core import deploy_docker

# Import refactored logic
from deploy_pkg.modes import deploy_sandbox, deploy_tauri


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MyrmAgent 部署脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
部署模式:
    tauri   桌面客户端模式（本地嵌入式数据库，单用户）
    sandbox 沙箱模式（控制平面管理的隔离实例）
    docker  Docker 全栈部署（后端 + 前端 + 依赖服务）

示例:
    uv run deploy.py tauri dev          # 桌面端开发模式
    uv run deploy.py tauri build        # 桌面端打包
    uv run deploy.py sandbox             # 沙箱模式
    uv run deploy.py docker             # Docker 全栈部署
    uv run deploy.py status             # 查看状态
    uv run deploy.py stop               # 停止服务
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="部署命令")

    tauri_parser = subparsers.add_parser("tauri", help="Tauri 桌面客户端模式")
    tauri_parser.add_argument("action", choices=["dev", "build"], default="dev", nargs="?", help="dev: 开发模式, build: 打包")

    subparsers.add_parser("sandbox", help="沙箱模式（控制平面管理）")
    subparsers.add_parser("docker", help="Docker 全栈部署（后端 + 前端 + 数据库）")
    subparsers.add_parser("status", help="查看服务状态")
    subparsers.add_parser("stop", help="停止所有服务")

    args = parser.parse_args()

    if args.command == "tauri":
        action = getattr(args, "action", "dev")
        success = deploy_tauri(action=action)
        sys.exit(0 if success else 1)
    elif args.command == "sandbox":
        success = deploy_sandbox()
        if success:
            start_application()
        sys.exit(0 if success else 1)
    elif args.command == "docker":
        success = deploy_docker()
        sys.exit(0 if success else 1)
    elif args.command == "status":
        show_status()
    elif args.command == "stop":
        stop_services()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
