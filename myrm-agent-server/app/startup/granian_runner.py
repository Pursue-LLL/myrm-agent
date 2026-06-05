"""
@input: 依赖 health_check 的「启动健康检查」，依赖 granian 外部库
@output: 对外提供 granian 多进程启动（仅适用于无嵌入式数据库的场景）
@pos: granian 服务器启动器 —— 多进程模式（可选）

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

import os
import subprocess
import sys

from app.startup.health_check import run_startup_health_check


def start_with_granian(
    host: str,
    port: int,
    skip_port_check: bool = False,
    skip_health_check: bool = False,
    no_auto_recovery: bool = False,
    force_recovery: bool = False,
) -> None:
    """使用 granian 启动（手动多进程模式，仅适用于无嵌入式数据库的场景）。"""
    # 运行健康检查
    run_startup_health_check(
        skip_health_check=skip_health_check,
        auto_recovery=not no_auto_recovery,
        force_recovery=force_recovery,
    )

    workers = int(os.getenv("GRANIAN_WORKERS", str(os.cpu_count() or 4)))

    print("🚀 Granian multi-process mode (SERVER_MODE=granian)")
    print("⚠️  Embedded SQLite/Qdrant may conflict with multi-process — use only with remote DB")
    print(f"📍 Starting server at http://{host}:{port}")
    print(f"💻 CPU cores: {os.cpu_count()}")
    print(f"👷 Workers: {workers}")

    # 设置环境变量供数据库工厂使用
    os.environ["GRANIAN_WORKERS"] = str(workers)
    os.environ["WEB_CONCURRENCY"] = str(workers)

    command = [
        "granian",
        "--interface",
        "asgi",
        "--host",
        host,
        "--port",
        str(port),
        "--workers",
        str(workers),
        "--runtime-mode",
        "mt",
        "--blocking-threads",
        "1",
        "--runtime-threads",
        "2",
        "app.main:app",
    ]

    try:
        subprocess.run(command, check=True)
    except FileNotFoundError:
        print("❌ Error: 'granian' command not found.")
        print("💡 Install sandbox deps: uv sync --group sandbox")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n📍 Server stopped by user")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print(f"❌ An error occurred while running granian: {e}")
        sys.exit(1)
